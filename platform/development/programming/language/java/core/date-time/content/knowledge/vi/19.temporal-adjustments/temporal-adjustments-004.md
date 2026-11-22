# Phân biệt next() với nextOrSame()

## 1. Khác biệt nằm ở việc có tính ngày hiện tại hay không

Khi yêu cầu là “tìm thứ Hai tiếp theo”, cần làm rõ: nếu hôm nay đã là thứ Hai thì giữ hôm nay hay chuyển sang tuần sau?

`TemporalAdjusters` cung cấp hai quy tắc khác nhau:

- `next(dayOfWeek)`: tìm ngày mang thứ yêu cầu **sau ngày đầu vào**, luôn tiến ít nhất một ngày.
- `nextOrSame(dayOfWeek)`: giữ ngày đầu vào nếu đã đúng thứ; nếu chưa đúng thì tìm ngày phù hợp gần nhất phía sau.

Với ngày thứ Hai 26/10/2026:

```text
next(MONDAY)       -> 2026-11-02
nextOrSame(MONDAY) -> 2026-10-26
```

Đây không phải hai tên đồng nghĩa. Điều kiện “hoặc chính ngày này” quyết định cách xử lý đúng tại ranh giới của lịch hẹn, kỳ báo cáo hay khoảng ngày đang xét.

## 2. Tạo quy tắc rồi áp dụng bằng with

Cả hai phương thức trả về `TemporalAdjuster`. Áp dụng quy tắc vào `LocalDate` qua `with(...)`:

```java
LocalDate date = LocalDate.of(2026, 10, 26);
LocalDate next = date.with(TemporalAdjusters.next(DayOfWeek.MONDAY));
LocalDate sameOrNext = date.with(
        TemporalAdjusters.nextOrSame(DayOfWeek.MONDAY));
```

`date` không bị thay đổi. Phải dùng kết quả trả về; gọi `date.with(...)` rồi bỏ kết quả không cập nhật biến. Các quy tắc có sẵn là bất biến, nên có thể giữ làm hằng khi dùng nhiều lần.

`DayOfWeek` biểu diễn đúng thứ trong tuần. Không cần dùng số kiểu `0` hoặc `1` rồi tự đoán cách đánh số của API khác. Theo quy ước của `DayOfWeek`, thứ Hai là 1 và Chủ nhật là 7; lựa chọn ngôn ngữ hiển thị không đổi nghĩa `MONDAY`.

Đoạn trên là ví dụ trong một phương thức Java. Chương trình chạy đầy đủ và các import cần thiết ở phần 6.

## 3. Nếu đầu vào chưa đúng thứ, hai cách cho cùng kết quả

Với đích là thứ Hai, xét các ngày từ 26/10 đến 01/11/2026:

| Ngày đầu vào | Thứ | next(MONDAY) | nextOrSame(MONDAY) |
|---|---|---|---|
| `2026-10-26` | Thứ Hai | `2026-11-02` | `2026-10-26` |
| `2026-10-27` | Thứ Ba | `2026-11-02` | `2026-11-02` |
| `2026-10-28` | Thứ Tư | `2026-11-02` | `2026-11-02` |
| `2026-10-29` | Thứ Năm | `2026-11-02` | `2026-11-02` |
| `2026-10-30` | Thứ Sáu | `2026-11-02` | `2026-11-02` |
| `2026-10-31` | Thứ Bảy | `2026-11-02` | `2026-11-02` |
| `2026-11-01` | Chủ nhật | `2026-11-02` | `2026-11-02` |

Chỉ hàng có ngày đầu vào đúng thứ đích mới khác. Nếu chỉ thử vào một ngày khác thứ đích, bạn có thể tưởng hai API luôn giống nhau và bỏ lỡ lỗi biên quan trọng nhất.

Trong lịch ISO, `next` dịch từ 1 đến 7 ngày; `nextOrSame` dịch từ 0 đến 6 ngày. Cả hai đều không lùi về quá khứ theo ngày và đều có thể vượt ranh giới tháng hoặc năm.

### Cách hình dung số ngày dịch chuyển

Gọi `current` là số thứ của ngày đầu vào, `target` là số thứ đích:

```text
delta = floorMod(target - current, 7)
```

`delta` nằm trong 0–6. `nextOrSame` dùng đúng khoảng cách đó; `next` thay trường hợp 0 thành 7. Đây là cách hiểu cơ chế cho lịch tuần bảy ngày, không phải lý do cần tự viết lại thư viện trong mã ứng dụng.

Vì thế, `plusDays(7)` chỉ trùng với `next(target)` khi ngày đầu vào đã đúng thứ đích. Nếu đầu vào là Chủ nhật và đích là thứ Hai, `next(MONDAY)` chỉ đi một ngày.

## 4. Chọn API theo ranh giới của yêu cầu

| Yêu cầu đã được làm rõ | Lựa chọn |
|---|---|
| Ngày đầu tiên là thứ Hai, tính cả ngày bắt đầu | `nextOrSame(MONDAY)` |
| Lần xuất hiện thứ Hai sau ngày hiện tại | `next(MONDAY)` |
| Chuẩn hóa một ngày thành thứ Hai gần nhất ở phía trước hoặc chính nó | `nextOrSame(MONDAY)` |
| Tạo lần lặp sau một ngày sự kiện đã diễn ra vào thứ Hai | `next(MONDAY)` |

Không mặc định `nextOrSame` tốt hơn vì có thêm một trường hợp. Nó có thể giữ đúng ngày sự kiện cũ trong khi chức năng cần kỳ tiếp theo. Ngược lại, `next` có thể bỏ mất ngày bắt đầu hợp lệ nếu hợp đồng cho phép dùng ngay ngày đó.

### Áp dụng lại có thể khác nhau

Với thứ Hai 26/10/2026:

```text
nextOrSame một lần: 2026-10-26
nextOrSame hai lần: 2026-10-26

next một lần:      2026-11-02
next hai lần:      2026-11-09
```

`nextOrSame` với cùng đích có tính lũy đẳng về giá trị: sau lần đầu đã đúng thứ, lần sau giữ nguyên. `next` thì mỗi lần tiếp tục sang lần xuất hiện sau. Cần lưu ý khi nhiều lớp cùng áp dụng quy tắc hoặc khi xử lý được thử lại.

Không nên dùng `==` để kiểm tra ngày có “giữ nguyên” về giá trị hay không. Dùng `equals`; điều quan trọng là ngày kết quả, không phải địa chỉ đối tượng.

## 5. Điều chỉnh thứ chưa đủ để tìm một lịch hẹn sau thời điểm hiện tại

Giả sử lịch hẹn diễn ra mỗi thứ Hai lúc 09:00. Nếu hiện tại là thứ Hai lúc 10:00, `nextOrSame(MONDAY)` vẫn giữ đúng ngày thứ Hai đó. Sau khi đặt giờ 09:00, ứng viên lại nằm trước thời gian đầu vào.

Còn nếu hiện tại là thứ Hai lúc 08:00, dùng `next(MONDAY)` ngay từ đầu sẽ bỏ lỡ lịch 09:00 cùng ngày vốn vẫn chưa tới.

Một chính sách rõ ràng cho ví dụ này là **lịch hẹn phải nằm sau thời gian đầu vào, không bao gồm đúng thời điểm ấy**:

1. Dùng `nextOrSame(MONDAY)` để tạo ngày ứng viên.
2. Đặt giờ ứng viên thành 09:00.
3. Nếu ứng viên không nằm sau đầu vào, cộng thêm một tuần.

Khi đầu vào đúng thứ Hai 09:00, chính sách trên chuyển sang tuần sau. Nếu chức năng muốn cho phép đúng thời điểm hiện tại, phải đổi điều kiện ranh giới tương ứng; không giao quyết định đó cho tên API.

Ví dụ này dùng `LocalDateTime` trong cùng một ngữ cảnh giờ địa phương. Nó chưa xử lý múi giờ, DST hoặc ngày nghỉ. Điều chỉnh ngày của một kiểu có múi giờ còn tuân theo quy tắc của kiểu đó; không được suy ra rằng dịch một ngày lịch luôn là đúng 24 giờ thực trôi qua.

## 6. Chương trình chạy đầy đủ

Lưu đoạn sau vào `NextAndNextOrSameDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài.

```java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.LocalTime;
import java.time.temporal.TemporalAdjuster;
import java.time.temporal.TemporalAdjusters;

public class NextAndNextOrSameDemo {
    private static final TemporalAdjuster NEXT_MONDAY =
            TemporalAdjusters.next(DayOfWeek.MONDAY);
    private static final TemporalAdjuster MONDAY_OR_SAME =
            TemporalAdjusters.nextOrSame(DayOfWeek.MONDAY);

    public static void main(String[] args) {
        LocalDate start = LocalDate.of(2026, 10, 26);
        for (int i = 0; i < 7; i++) {
            LocalDate date = start.plusDays(i);
            System.out.println(date + " " + date.getDayOfWeek()
                    + " next=" + date.with(NEXT_MONDAY)
                    + " orSame=" + date.with(MONDAY_OR_SAME));
        }

        LocalDate once = start.with(MONDAY_OR_SAME);
        System.out.println("orSameTwice=" + once.with(MONDAY_OR_SAME));
        System.out.println("nextTwice="
                + start.with(NEXT_MONDAY).with(NEXT_MONDAY));
        System.out.println("original=" + start);

        LocalDateTime before = start.atTime(8, 0);
        LocalDateTime after = start.atTime(10, 0);
        LocalDateTime exactly = start.atTime(9, 0);
        System.out.println("before=" + nextMondayAtNine(before));
        System.out.println("after=" + nextMondayAtNine(after));
        System.out.println("exactly=" + nextMondayAtNine(exactly));
    }

    private static LocalDateTime nextMondayAtNine(LocalDateTime now) {
        LocalDateTime candidate = now.with(MONDAY_OR_SAME)
                .with(LocalTime.of(9, 0));
        if (!candidate.isAfter(now)) {
            candidate = candidate.plusWeeks(1);
        }
        return candidate;
    }
}
```

Biên dịch và chạy:

```shell
javac NextAndNextOrSameDemo.java
java NextAndNextOrSameDemo
```

Kết quả chuẩn:

```text
2026-10-26 MONDAY next=2026-11-02 orSame=2026-10-26
2026-10-27 TUESDAY next=2026-11-02 orSame=2026-11-02
2026-10-28 WEDNESDAY next=2026-11-02 orSame=2026-11-02
2026-10-29 THURSDAY next=2026-11-02 orSame=2026-11-02
2026-10-30 FRIDAY next=2026-11-02 orSame=2026-11-02
2026-10-31 SATURDAY next=2026-11-02 orSame=2026-11-02
2026-11-01 SUNDAY next=2026-11-02 orSame=2026-11-02
orSameTwice=2026-10-26
nextTwice=2026-11-09
original=2026-10-26
before=2026-10-26T09:00
after=2026-11-02T09:00
exactly=2026-11-02T09:00
```

Vòng lặp bao phủ cả tuần, đặc biệt có ngày đầu vào đúng thứ đích. Các dòng `before`, `after` và `exactly` chứng minh phép kiểm tra giờ là một bước riêng sau khi tìm ngày ứng viên. Dòng `original` cho thấy các phép điều chỉnh không thay đổi ngày ban đầu.

## 7. Những cách dùng dễ gây nhầm

- **Thấy hôm nay đã đúng thứ nên nghĩ next sẽ giữ lại:** `next` chủ động loại ngày hiện tại; cần `nextOrSame` nếu muốn bao gồm nó.
- **Dùng nextOrSame để tạo mọi kỳ tiếp theo:** khi đầu vào đã là ngày của kỳ cũ, kết quả có thể không tiến lên.
- **Chọn next chỉ vì một cuộc hẹn phải ở tương lai:** nếu hôm nay đúng thứ và giờ hẹn vẫn còn phía trước, có thể cần giữ hôm nay rồi so sánh giờ.
- **Thay bằng `with(DayOfWeek.MONDAY)`:** đây là phép điều chỉnh trường thứ theo ngữ nghĩa khác, có thể lùi trong tuần; không tương đương tìm thứ Hai tiếp theo.
- **Cho rằng thứ Hai luôn là ngày làm việc:** hai API chỉ xét thứ trong tuần, không biết ngày lễ hoặc lịch hoạt động của tổ chức.
- **Cho rằng kết quả phải ở cùng tháng:** tìm thứ tiếp theo có thể sang tháng và năm mới; đó là hành vi bình thường.

Đầu vào và kiểu ngày giờ phải hỗ trợ các trường/đơn vị cần thiết. Gần giới hạn cực đại của kiểu, nếu không còn ngày phù hợp trong miền biểu diễn thì phép điều chỉnh gây ngoại lệ, không tự quay về đầu lịch.

## 8. Tự thực hành

Đổi đích sang `DayOfWeek.FRIDAY` và dự đoán trước khi chạy:

| Đầu vào | next(FRIDAY) | nextOrSame(FRIDAY) |
|---|---|---|
| `2026-10-29` (thứ Năm) | `2026-10-30` | `2026-10-30` |
| `2026-10-30` (thứ Sáu) | `2026-11-06` | `2026-10-30` |
| `2026-10-31` (thứ Bảy) | `2026-11-06` | `2026-11-06` |

Sau đó đổi điều kiện trong `nextMondayAtNine` từ `!candidate.isAfter(now)` thành `candidate.isBefore(now)`. Chỉ ra vì sao đầu vào đúng 09:00 thay đổi kết quả, còn đầu vào 08:00 và 10:00 vẫn tuân theo cách chọn ngày tương ứng.

Câu hỏi quyết định khi chọn giữa hai API là: **ngày đầu vào có được phép là đáp án không?** Khi bài toán có thêm giờ hẹn, hãy trả lời tiếp rằng toàn bộ ngày-giờ kết quả có được bằng đầu vào không.

Tham khảo: [TemporalAdjusters — next và nextOrSame](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAdjusters.html) trong Java SE 21.
