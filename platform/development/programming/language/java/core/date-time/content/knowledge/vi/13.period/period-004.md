# Phân biệt thành phần `getDays()` với tổng số ngày

## Hai câu hỏi trông giống nhau nhưng cần hai kết quả khác nhau

Giả sử một người bắt đầu học ngày 15/01/2024 và xem lại tiến độ ngày 20/03/2024. Ta có thể muốn biết:

- Khoảng cách theo lịch được mô tả bằng bao nhiêu năm, tháng và ngày?
- Hai ngày này cách nhau tổng cộng bao nhiêu ngày lịch?

Câu trả lời thứ nhất là **2 tháng 5 ngày**; câu trả lời thứ hai là **65 ngày**. Cả hai đều đúng, nhưng phục vụ mục đích khác nhau. Lỗi xuất hiện khi lấy riêng số `5` trong mô tả thứ nhất để trả lời câu hỏi thứ hai.

Trong bài này, “tổng số ngày” là khoảng cách có hướng giữa hai `LocalDate`, theo quy ước đầu bao gồm, cuối không bao gồm: `[start, end)`. Đây là phép đếm ngày lịch, chưa phải số khối 24 giờ thực sự trôi qua giữa hai thời điểm.

## 1. Mô hình đúng: `Period` giữ ba thành phần

`Period` biểu diễn một lượng thời gian theo lịch ISO bằng ba thành phần năm, tháng và ngày. `getDays()` chỉ đọc thành phần ngày; `get(ChronoUnit.DAYS)` cũng không cộng dồn năm hoặc tháng. Đối với một `Period` tự tạo, thành phần ngày có thể lớn hoặc âm. Ví dụ, `Period.ofDays(40).getDays()` bằng `40`. [Tài liệu `Period`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Period.html#getDays())

Có thể hình dung:

```text
Period P2M5D
        │ │
        │ └── days   = 5
        └──── months = 2
              years  = 0
```

Chữ `P` mở đầu biểu diễn chuỗi của một `Period`; `M` và `D` ở đây là tháng và ngày. Đọc `P2M5D` là “2 tháng 5 ngày”, không phải “5 ngày tổng cộng”.

Đoạn minh họa sau giả định đã import `java.time.Period`:

```java
Period period = Period.of(0, 2, 5);

int years = period.getYears();   // 0
int months = period.getMonths(); // 2
int dayComponent = period.getDays(); // 5
```

Tên `dayComponent` diễn đạt đúng dữ liệu đang giữ. Đặt tên biến này là `totalDays` khiến mã dễ bị dùng sai dù chương trình vẫn biên dịch bình thường.

## 2. Khi tính giữa hai ngày, “phần ngày” là phần sau các tháng trọn vẹn

`Period.between(start, end)` xác định các tháng trọn vẹn, tính phần ngày còn lại rồi tách tháng thành năm và tháng. Vì vậy, đọc `getDays()` từ kết quả chỉ cho phần ngày trong cách phân rã đó. [Tài liệu `Period.between`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Period.html#between(java.time.LocalDate,java.time.LocalDate))

Với ví dụ đầu bài:

```text
2024-01-15 ── 2 tháng ──> 2024-03-15 ── 5 ngày ──> 2024-03-20
```

Nếu mục tiêu là hiển thị “đã học được 2 tháng 5 ngày”, giữ `Period` và đọc các thành phần là phù hợp.

Nếu mục tiêu là hiển thị “hai mốc cách nhau 65 ngày”, hãy tính trực tiếp:

```java
long totalDays = ChronoUnit.DAYS.between(start, end);
```

Khi hai đối số là `LocalDate`, cách viết tương đương là:

```java
long totalDays = start.until(end, ChronoUnit.DAYS);
```

Trong cả hai đoạn này, `start` và `end` là hai biến `LocalDate` đã có; cần import `java.time.temporal.ChronoUnit`. Phép tính `between` trả về số đơn vị trọn vẹn có hướng từ đầu đến cuối. [Tài liệu `ChronoUnit.between`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/ChronoUnit.html#between(java.time.temporal.Temporal,java.time.temporal.Temporal))

## 3. Chương trình hoàn chỉnh để nhìn thấy sự khác biệt

Lưu dưới tên `PeriodDaysDemo.java`. Ví dụ dùng Java 17 trở lên, chỉ sử dụng thư viện chuẩn:

```java
import java.time.LocalDate;
import java.time.Period;
import java.time.temporal.ChronoUnit;

public class PeriodDaysDemo {
    public static void main(String[] args) {
        LocalDate start = LocalDate.of(2024, 1, 15);
        LocalDate end = LocalDate.of(2024, 3, 20);

        Period period = Period.between(start, end);
        long totalDays = ChronoUnit.DAYS.between(start, end);

        System.out.println("period=" + period);
        System.out.println("years=" + period.getYears());
        System.out.println("months=" + period.getMonths());
        System.out.println("dayComponent=" + period.getDays());
        System.out.println("totalDays=" + totalDays);
        System.out.println("rebuiltEnd=" + start.plus(period));

        LocalDate february = LocalDate.of(2024, 2, 1);
        LocalDate march = LocalDate.of(2024, 3, 1);
        LocalDate april = LocalDate.of(2024, 4, 1);

        System.out.println("februaryPeriod="
                + Period.between(february, march));
        System.out.println("marchPeriod="
                + Period.between(march, april));
        System.out.println("februaryDays="
                + ChronoUnit.DAYS.between(february, march));
        System.out.println("marchDays="
                + ChronoUnit.DAYS.between(march, april));

        System.out.println("reversedDays="
                + ChronoUnit.DAYS.between(end, start));
        System.out.println("sameDateDays="
                + ChronoUnit.DAYS.between(start, start));

        Period fortyDays = Period.ofDays(40);
        System.out.println("fortyDayComponent=" + fortyDays.getDays());
        System.out.println("normalizedFortyDays=" + fortyDays.normalized());
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp:

```shell
javac --release 17 PeriodDaysDemo.java
java PeriodDaysDemo
```

Stdout:

```text
period=P2M5D
years=0
months=2
dayComponent=5
totalDays=65
rebuiltEnd=2024-03-20
februaryPeriod=P1M
marchPeriod=P1M
februaryDays=29
marchDays=31
reversedDays=-65
sameDateDays=0
fortyDayComponent=40
normalizedFortyDays=P40D
```

Giải thích các nhóm kết quả:

- `P2M5D` và `65` cùng mô tả khoảng cách giữa hai mốc, nhưng một bên giữ các đơn vị lịch, bên kia đếm ngày.
- Hai khoảng tháng 02 và tháng 03 đều cho `P1M`; tổng ngày lần lượt là `29` và `31`. Năm 2024 có ngày 29/02.
- Đảo hai mốc cho số ngày `-65`; hai mốc giống nhau cho `0`.
- `P40D` vẫn giữ thành phần ngày bằng `40` sau khi gọi `normalized()`.

## 4. Vì sao không thể đổi mọi `Period` thành tổng số ngày nếu thiếu ngày neo?

Một tháng bắt đầu từ 01/02/2024 kết thúc tại 01/03/2024; một tháng bắt đầu từ 01/03/2024 kết thúc tại 01/04/2024. Trong chương trình, cùng lượng lịch `P1M` tương ứng lần lượt với 29 và 31 ngày.

Do đó, nếu chỉ được đưa `Period.ofMonths(1)`, câu hỏi “tổng cộng bao nhiêu ngày?” còn thiếu **ngày neo**: ngày bắt đầu áp dụng lượng lịch đó.

Nếu đã có hai mốc ban đầu, hãy dùng trực tiếp hai mốc. Nếu chỉ có `Period` và một ngày neo có ý nghĩa trong nghiệp vụ, hãy tạo ngày kết thúc trước:

```java
LocalDate anchor = LocalDate.of(2024, 2, 1);
Period amount = Period.ofMonths(1);

LocalDate target = anchor.plus(amount);
long totalDaysAtAnchor = ChronoUnit.DAYS.between(anchor, target);
// target = 2024-03-01
// totalDaysAtAnchor = 29
```

Đây là đoạn minh họa, dùng các import như chương trình hoàn chỉnh ở trên. Kết quả `29` thuộc về **lượng lịch cùng ngày neo này**, không phải một thuộc tính cố định của `P1M`.

Khi thiết kế dữ liệu cho ứng dụng theo dõi học tập, chẳng hạn, hai trường `startedOn` và `reviewedOn` giữ đủ thông tin để vừa tính khoảng cách ngày vừa mô tả năm/tháng/ngày. Nếu chỉ lưu chuỗi `P1M`, ứng dụng không thể tự biết người dùng đang nói tới tháng nào.

Với lượng lịch chỉ có thành phần ngày, chẳng hạn `Period.ofDays(40)`, `getDays()` đúng bằng số ngày của lượng đó. Điều kiện này không cho phép suy rộng sang lượng có thành phần năm hoặc tháng.

## 5. Những cách sửa trông hợp lý nhưng vẫn sai ý nghĩa

### Gọi `normalized()` rồi lấy `getDays()`

`normalized()` chuẩn hóa năm và tháng; thành phần ngày được giữ nguyên. Nó không đổi tháng thành ngày. [Tài liệu `Period.normalized`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Period.html#normalized())

Vì vậy, trong chương trình, `Period.ofDays(40).normalized()` vẫn là `P40D`. Với khoảng `P2M5D`, gọi chuẩn hóa cũng không làm `getDays()` trở thành `65`.

### Tự nhân năm với 365 và tháng với 30

Đoạn sau chỉ minh họa công thức **không phù hợp để đếm chính xác ngày lịch**:

```java
long guessedDays = period.getYears() * 365L
        + period.getMonths() * 30L
        + period.getDays();
```

Với `P2M5D` trong chương trình, công thức cho `65`, tình cờ trùng đáp án. Nhưng áp dụng cho `P1M` của tháng 02 hoặc tháng 03 đều cho `30`, trong khi kết quả quan sát được là `29` và `31`. Một ví dụ chạy đúng không chứng minh công thức đúng cho lịch.

Nếu nghiệp vụ có quy ước tháng 30 ngày riêng, hãy đặt tên và mô tả rõ quy ước đó; đừng trình bày kết quả như khoảng cách ngày lịch thực tế.

### Cho rằng có phương thức `Period.toTotalDays()`

`Period` không có phương thức này. `toTotalMonths()` có tồn tại, nhưng trả về tổng tháng tính từ năm và tháng, không giải quyết việc đếm ngày giữa hai mốc. Khi cần ngày, quay lại `LocalDate` và `ChronoUnit.DAYS.between`. [Danh sách phương thức `Period`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Period.html)

### Thấy `getDays() == 0` rồi kết luận khoảng cách bằng không

Trong chương trình, cả `P1M` của tháng 02 và tháng 03 đều có thành phần ngày bằng `0`, dù hai mốc rõ ràng khác nhau. Nếu muốn kiểm tra mọi thành phần của một `Period` đều bằng không, dùng `isZero()`; nếu muốn biết hai ngày có trùng nhau, so sánh hai `LocalDate` trực tiếp. [Tài liệu `Period.isZero`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Period.html#isZero())

## 6. Chốt quy ước đầu/cuối trước khi đặt tên “tổng ngày”

Với quy ước `[start, end)`:

| Ngày đầu | Ngày cuối | `DAYS.between` |
| --- | --- | ---: |
| 2024-06-01 | 2024-06-01 | 0 |
| 2024-06-01 | 2024-06-02 | 1 |
| 2024-06-02 | 2024-06-01 | -1 |

Ví dụ một chương trình học diễn ra từ ngày 01/06 đến hết ngày 02/06 có **hai ngày được lên lịch**, dù khoảng cách giữa hai nhãn ngày là một ngày.

Khi nghiệp vụ yêu cầu đếm cả hai đầu và đã bảo đảm `end` không trước `start`, có thể viết:

```java
long scheduledDateCount = ChronoUnit.DAYS.between(start, end) + 1;
```

Đây là một quy ước đếm khác. Không tự cộng `1` vào mọi phép tính khoảng cách; đặc biệt phải xử lý hoặc từ chối khoảng đảo chiều trước khi áp dụng quy tắc đếm cả hai đầu.

Ngoài ra, bài này dùng `LocalDate`, vốn không giữ giờ hay múi giờ. Nếu câu hỏi thực sự là “bao nhiêu giờ đã trôi qua giữa hai thời điểm?”, cần giữ dữ liệu thời điểm thích hợp và thực hiện phép đo tương ứng; không lấy kết quả ngày lịch của bài này rồi mặc định nhân `24` cho mọi tình huống.

## 7. Chọn phép tính theo đầu ra cần dùng

| Đầu ra mong muốn | Cách làm |
| --- | --- |
| “2 tháng 5 ngày” | `Period.between(start, end)` rồi đọc các thành phần |
| Riêng phần ngày trong mô tả năm/tháng/ngày | `period.getDays()` |
| Khoảng cách ngày lịch có hướng giữa hai ngày | `ChronoUnit.DAYS.between(start, end)` |
| Tổng ngày ứng với lượng lịch và ngày neo xác định | Tạo `target = anchor.plus(period)`, rồi đếm giữa `anchor` và `target` |

Ở nơi sử dụng kết quả, ưu tiên các tên như `dayComponent`, `elapsedCalendarDays` hoặc `scheduledDateCount` thay cho một biến `days` mơ hồ. Tên biến nên cho người đọc biết cả đại lượng lẫn quy ước đếm.

## 8. Tự kiểm tra cách hiểu

1. `Period.between(2024-02-01, 2024-03-01)` cho `P1M`. `getDays()` bằng bao nhiêu? Khoảng cách ngày bằng bao nhiêu?
2. Một đoạn mã chỉ có `Period.ofMonths(2)` nhưng muốn trả về một tổng ngày chính xác. Đầu vào đang thiếu gì?
3. Vì sao `Period.ofDays(40).getDays()` bằng `40` không mâu thuẫn với việc `getDays()` là thành phần?
4. Có nên dùng `getDays() == 0` để kiểm tra hai ngày trùng nhau không?

Đáp án và lý do:

1. Thành phần ngày bằng `0`, khoảng cách bằng `29` ngày. Tháng được lưu ở thành phần tháng.
2. Thiếu ngày neo hoặc hai mốc ngày thực tế để xác định hai tháng đó đi qua những ngày nào.
3. Vì toàn bộ lượng này được biểu diễn bằng thành phần ngày; năm và tháng đều bằng không.
4. Không. Một khoảng như `P1M` cũng có thành phần ngày bằng `0`. Hãy so sánh hai ngày trực tiếp, hoặc dùng đúng phép đếm ngày theo yêu cầu.
