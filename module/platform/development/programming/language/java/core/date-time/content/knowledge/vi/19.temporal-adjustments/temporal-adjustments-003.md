# Tìm thứ kế tiếp hoặc trước đó

## 1. Xác định có tính ngày hiện tại hay không

Giả sử cần tìm thứ Sáu để chốt báo cáo. Nếu hôm nay là thứ Tư, “thứ Sáu kế tiếp” khá rõ ràng. Nhưng nếu hôm nay đã là thứ Sáu, yêu cầu có thể mang hai ý nghĩa: chọn ngay hôm nay hoặc chọn thứ Sáu tuần sau. Sự khác biệt này quyết định dữ liệu trả về, không chỉ là cách đặt tên.

`java.time.temporal.TemporalAdjusters` cung cấp bốn phép điều chỉnh tương ứng: `next()`, `nextOrSame()`, `previous()`, `previousOrSame()`. Chúng nhận một `DayOfWeek` và trả về quy tắc điều chỉnh `TemporalAdjuster`; ta áp dụng quy tắc bằng `date.with(adjuster)`.

Các quan hệ trước/sau và việc có nhận ngày gốc được mô tả tại [Java SE 21 — TemporalAdjusters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAdjusters.html). Với `LocalDate`, có thể chọn theo bảng:

| Phương thức | Điều kiện của ngày kết quả so với ngày gốc | Nếu ngày gốc đúng thứ cần tìm | Số ngày dịch chuyển |
| --- | --- | --- | --- |
| `next(dayOfWeek)` | Sau ngày gốc | Tiến 7 ngày | +1 đến +7 |
| `nextOrSame(dayOfWeek)` | Sau hoặc bằng ngày gốc | Giữ ngày đó | 0 đến +6 |
| `previous(dayOfWeek)` | Trước ngày gốc | Lùi 7 ngày | -7 đến -1 |
| `previousOrSame(dayOfWeek)` | Trước hoặc bằng ngày gốc | Giữ ngày đó | -6 đến 0 |

Câu hỏi cần trả lời trước khi viết mã là: **mốc đầu có được nằm trong kết quả hay không?** Không chọn theo cảm giác rằng tên “kế tiếp” luôn bao gồm hoặc luôn loại hôm nay trong mọi yêu cầu nghiệp vụ.

## 2. Cách dùng với `LocalDate`

Ví dụ minh họa trong một phương thức:

```java
LocalDate date = LocalDate.of(2025, 6, 11);
LocalDate friday = date.with(TemporalAdjusters.next(DayOfWeek.FRIDAY));
```

Ngày `2025-06-11` là thứ Tư, nên kết quả là `2025-06-13`. `LocalDate` là bất biến; cần dùng giá trị trả về. Chỉ gọi `date.with(...)` rồi bỏ kết quả không làm biến `date` trỏ tới ngày thứ Sáu.

Có thể giữ một quy tắc dùng nhiều lần:

```java
TemporalAdjuster nextFriday = TemporalAdjusters.next(DayOfWeek.FRIDAY);
LocalDate result = date.with(nextFriday);
```

Quy tắc mô tả cách tìm ngày chứ không giữ một ngày thứ Sáu cố định. Áp dụng cùng `nextFriday` lên những ngày khác nhau sẽ tính kết quả theo từng ngày đầu vào.

## 3. Hiểu khoảng cách theo chu kỳ bảy ngày

Không cần tự viết vòng lặp tăng từng ngày để dùng các API trên. Tuy vậy, hiểu cách tính giúp nhận diện lỗi lệch một tuần.

Theo [Java SE 21 — DayOfWeek](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/DayOfWeek.html), `getValue()` dùng quy ước ISO: thứ Hai bằng 1, ..., Chủ nhật bằng 7. Không dùng `ordinal()` thay cho giá trị này.

Gọi `current` là số thứ của ngày gốc và `target` là số thứ cần tìm:

```text
Khoảng tiến cho nextOrSame = (target - current + 7) % 7
Khoảng lùi cho previousOrSame = (current - target + 7) % 7
```

Nếu dùng bản loại ngày gốc là `next()` hoặc `previous()`, khoảng cách 0 được đổi thành 7. Ví dụ, từ thứ Tư (3) tới thứ Sáu (5) là 2 ngày; từ thứ Sáu tới thứ Sáu là 0 ngày nếu cho phép giữ nguyên và 7 ngày nếu phải tiến/lùi thật sự.

Công thức chỉ minh họa chu kỳ thứ trong tuần. Trong mã ứng dụng, ưu tiên API chuẩn để ý nghĩa “trước/sau hoặc bằng” được đọc trực tiếp từ tên phương thức. Tháng và năm có thể đổi khi cộng/trừ ngày; không giới hạn kết quả trong tháng của đầu vào.

## 4. Chương trình kiểm chứng đầy đủ

Lưu mã vào `NextPreviousWeekdayDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài:

```java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.temporal.TemporalAdjuster;
import java.time.temporal.TemporalAdjusters;

public class NextPreviousWeekdayDemo {
    private static void show(LocalDate date) {
        DayOfWeek target = DayOfWeek.FRIDAY;
        System.out.println("base = " + date + " " + date.getDayOfWeek());
        System.out.println("next Friday = "
                + date.with(TemporalAdjusters.next(target)));
        System.out.println("next or same = "
                + date.with(TemporalAdjusters.nextOrSame(target)));
        System.out.println("previous Friday = "
                + date.with(TemporalAdjusters.previous(target)));
        System.out.println("previous or same = "
                + date.with(TemporalAdjusters.previousOrSame(target)));
    }

    public static void main(String[] args) {
        show(LocalDate.of(2025, 6, 11));
        show(LocalDate.of(2025, 6, 13));

        LocalDate wednesday = LocalDate.of(2025, 6, 11);
        System.out.println("with Monday = "
                + wednesday.with(DayOfWeek.MONDAY));
        System.out.println("next Monday = "
                + wednesday.with(TemporalAdjusters.next(DayOfWeek.MONDAY)));
        System.out.println("across year = " + LocalDate.of(2025, 12, 31)
                .with(TemporalAdjusters.next(DayOfWeek.MONDAY)));

        TemporalAdjuster nextFriday = TemporalAdjusters.next(DayOfWeek.FRIDAY);
        LocalDate occurrence = wednesday.with(nextFriday);
        for (int i = 1; i <= 4; i++) {
            System.out.println("occurrence " + i + " = " + occurrence);
            occurrence = occurrence.with(nextFriday);
        }

        LocalDateTime now = LocalDateTime.of(2025, 6, 13, 18, 0);
        LocalDate candidateDate = now.toLocalDate()
                .with(TemporalAdjusters.nextOrSame(DayOfWeek.FRIDAY));
        LocalDateTime candidate = candidateDate.atTime(LocalTime.of(17, 0));
        if (!candidate.isAfter(now)) {
            candidate = candidate.plusWeeks(1);
        }
        System.out.println("next Friday 17:00 = " + candidate);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 NextPreviousWeekdayDemo.java
java NextPreviousWeekdayDemo
```

Kết quả:

```text
base = 2025-06-11 WEDNESDAY
next Friday = 2025-06-13
next or same = 2025-06-13
previous Friday = 2025-06-06
previous or same = 2025-06-06
base = 2025-06-13 FRIDAY
next Friday = 2025-06-20
next or same = 2025-06-13
previous Friday = 2025-06-06
previous or same = 2025-06-13
with Monday = 2025-06-09
next Monday = 2025-06-16
across year = 2026-01-05
occurrence 1 = 2025-06-13
occurrence 2 = 2025-06-20
occurrence 3 = 2025-06-27
occurrence 4 = 2025-07-04
next Friday 17:00 = 2025-06-20T17:00
```

Chương trình dùng các mốc cố định để kết quả không thay đổi theo ngày chạy. Phần in `WEDNESDAY`, `FRIDAY` là tên hằng enum, không phải văn bản tiếng Việt đã định dạng.

## 5. Ba tình huống dễ dùng nhầm

### Đặt thứ trong tuần khác với tìm lần xuất hiện sau đó

`wednesday.with(DayOfWeek.MONDAY)` đưa ngày về thứ Hai trong cùng tuần ISO, nên từ `2025-06-11` nhận `2025-06-09`. Trong khi đó, `with(next(MONDAY))` phải đi về phía sau nên nhận `2025-06-16`.

Nếu yêu cầu là thứ Hai sắp tới, đừng chỉ thay giá trị `DayOfWeek` rồi giả định luôn tiến. Việc chỉnh trường thứ trong cùng tuần và việc tìm lần xuất hiện kế tiếp là hai câu hỏi khác nhau.

### Tìm lần gần nhất không đồng nghĩa luôn dùng `previous()`

Nếu yêu cầu là “thứ Sáu gần nhất không muộn hơn ngày chốt”, phải dùng `previousOrSame(FRIDAY)`. Ngày chốt đã là thứ Sáu thì kết quả đúng là chính ngày đó; `previous(FRIDAY)` sẽ lùi một tuần.

Ngược lại, nếu cần “thứ Sáu ngay trước ngày chốt, loại ngày chốt”, `previous(FRIDAY)` mới đúng. Những từ như “gần nhất” trong mô tả nghiệp vụ cần được chuyển thành quan hệ rõ ràng: trước, sau, trước hoặc bằng, sau hoặc bằng. Bốn API không tự chọn ngày có khoảng cách tuyệt đối nhỏ nhất ở cả hai phía.

### Thứ kế tiếp có thể ở tháng hoặc năm khác

Từ `2025-12-31`, thứ Hai kế tiếp là `2026-01-05`. Không cần tự tăng tháng hoặc tự xử lý cuối năm. Nếu yêu cầu thêm điều kiện “chỉ trong tháng này”, phải kiểm tra điều kiện đó sau khi tìm, hoặc dùng phép điều chỉnh khác mô tả đúng phạm vi tháng. `next()` không chứa giới hạn tháng ngầm định.

## 6. Sinh nhiều ngày lặp và bảo đảm tiến

Trong chương trình, lần đầu áp dụng `nextFriday` lên thứ Tư cho ngày 13 tháng 6. Sau mỗi lần in, áp dụng `nextFriday` lên kết quả hiện tại để đi tới thứ Sáu tiếp theo: 20, 27 tháng 6, rồi 4 tháng 7.

Nếu thay bước cập nhật bằng `nextOrSame(FRIDAY)`, khi `occurrence` đã là thứ Sáu, nó sẽ giữ nguyên ngày. Một vòng lặp có điều kiện dừng theo ngày có thể không bao giờ tiến tới mốc dừng. Vì vậy:

- Lần đầu có thể dùng `nextOrSame()` nếu muốn tính cả ngày đầu.
- Sau khi đã có một lần xuất hiện, dùng `next()` hoặc cộng một tuần cho bước kế tiếp.
- Với chiều lùi, áp dụng ý tương tự bằng `previous()` để bảo đảm giảm ngày.

Đây là việc tính danh sách ngày. Các API này không tự tạo một bộ lập lịch chạy công việc, không đặt hẹn giờ và không quản lý trạng thái tác vụ.

## 7. Ngày phù hợp chưa chắc là thời điểm phù hợp

Phần cuối chương trình xét yêu cầu “thứ Sáu lúc 17:00 kế tiếp, phải sau mốc hiện tại”. Mốc hiện tại được cố định là thứ Sáu `2025-06-13` lúc 18:00. `nextOrSame(FRIDAY)` cho đúng ngày thứ Sáu hiện tại, nhưng ghép 17:00 sẽ tạo một thời gian đã qua.

Vì vậy chương trình làm hai bước:

1. Tìm ngày ứng viên có thể bao gồm hôm nay rồi ghép giờ 17:00.
2. Nếu ứng viên không sau mốc hiện tại, cộng một tuần.

Điều kiện `!candidate.isAfter(now)` còn loại trường hợp bằng đúng mốc hiện tại, đúng với yêu cầu “phải sau”. Nếu nghiệp vụ cho phép chạy ngay tại mốc bằng nhau, điều kiện phải được chọn lại cho phù hợp.

Ví dụ này dùng `LocalDateTime`, nên diễn đạt một quy tắc theo ngày–giờ địa phương chưa có vùng. Khi cần thời điểm thực trên dòng thời gian, phải xác định vùng/độ lệch và cách xử lý những ngày có chuyển đổi độ lệch. Không thể suy ra rằng mọi hai lần cách nhau một tuần lịch luôn cách nhau đúng 168 giờ ở mọi vùng thời gian.

## 8. Giới hạn và cách tự kiểm tra

Các phép điều chỉnh chỉ xét thứ trong tuần. Chúng không biết ngày lễ, ngày nghỉ riêng hoặc lịch đóng cửa doanh nghiệp. “Thứ Sáu kế tiếp” có thể rơi vào ngày lễ; nếu yêu cầu “ngày làm việc kế tiếp”, cần thêm lịch và quy tắc nghiệp vụ tương ứng.

Không để `Locale` hoặc cách trình bày lịch khiến bạn đổi nhầm số thứ. `DayOfWeek` vẫn theo giá trị ISO; để mã dễ đọc, dùng `DayOfWeek.MONDAY`, `FRIDAY` thay cho những số tự quy ước. Thay ngôn ngữ hiển thị không thay quan hệ ngày kế tiếp/trước đó của các adjuster.

Khi kiểm tra một hàm tìm thứ, tối thiểu hãy có hai trường hợp: ngày gốc khác thứ đích và ngày gốc đã đúng thứ đích. Bổ sung trường hợp đi qua tháng/năm nếu kết quả được dùng cho báo cáo theo kỳ. Đây là những tình huống giúp phát hiện sai khác giữa bản thường và bản `OrSame` nhanh hơn chỉ thử một ngày giữa tuần.

Bài tập: với ngày Chủ nhật `2025-06-15`, tìm thứ Hai kế tiếp và thứ Hai trước đó. Kết quả lần lượt là `2025-06-16` và `2025-06-09`. Sau đó đổi ngày gốc thành thứ Hai `2025-06-16`: `next(MONDAY)` phải cho ngày 23, còn `nextOrSame(MONDAY)` giữ ngày 16. Giải thích được sự thay đổi này là bạn đã xác định đúng việc có tính ngày gốc hay không.
