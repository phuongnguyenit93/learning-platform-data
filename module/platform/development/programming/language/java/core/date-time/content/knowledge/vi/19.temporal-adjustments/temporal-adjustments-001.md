# TemporalAdjuster và phép biến đổi theo quy tắc

## 1. Từ cộng một lượng sang tìm ngày theo một quy tắc

Trong xử lý ngày tháng, có yêu cầu nói rõ một lượng: “thêm 7 ngày”, “bớt 2 tháng”. Có yêu cầu lại mô tả một đích theo lịch: “ngày cuối tháng”, “thứ Hai tiếp theo”, “ngày tiếp theo không rơi vào cuối tuần”. Đích thứ hai cần một **quy tắc điều chỉnh**, không chỉ một con số.

`TemporalAdjuster` biểu diễn một quy tắc biến đổi đối tượng thời gian thành một kết quả phù hợp. Bạn có thể đặt tên cho quy tắc, tái sử dụng nó và áp dụng qua `with(adjuster)`.

Ví dụ:

```java
LocalDate date = LocalDate.of(2026, 10, 25);
LocalDate monthEnd = date.with(TemporalAdjusters.lastDayOfMonth());
```

`monthEnd` là `2026-10-31`; `date` vẫn là `2026-10-25`. Không cần tự viết bảng số ngày của từng tháng hay tự kiểm tra năm nhuận.

Đoạn trên minh họa trong một phương thức Java; chương trình độc lập với import và kết quả đầy đủ nằm ở phần 7.

## 2. Ba vai trò cần phân biệt

| Thành phần | Vai trò | Ví dụ |
|---|---|---|
| Đối tượng ngày giờ | Giá trị được áp dụng quy tắc | `LocalDate`, `LocalDateTime` |
| `TemporalAdjuster` | Giao diện mô tả một quy tắc | Quy tắc tìm ngày cuối tháng |
| `TemporalAdjusters` | Lớp tiện ích cung cấp các quy tắc có sẵn và hàm hỗ trợ | `lastDayOfMonth()`, `next(...)`, `ofDateAdjuster(...)` |

`TemporalAdjuster` là giao diện hàm, có một phương thức trừu tượng:

```java
Temporal adjustInto(Temporal temporal);
```

Đây là chữ ký API, không phải một chương trình độc lập. `Temporal` đại diện đối tượng thời gian có thể được điều chỉnh bằng các trường hoặc đơn vị được hỗ trợ; nó khác với `TemporalAccessor`, vốn tập trung vào việc đọc thông tin thời gian.

Quy tắc được tách khỏi nơi sử dụng, tương tự cách đóng gói một chiến lược xử lý. Nơi gọi chỉ cần biết “áp dụng quy tắc ngày cuối tháng”, thay vì chứa toàn bộ thuật toán xác định ngày ấy.

Không phải mọi `TemporalAdjuster` đều dành riêng cho ngày. Có các đối tượng và quy tắc điều chỉnh phần giờ hoặc độ lệch. Phạm vi bài này tập trung vào các quy tắc ngày theo lịch ISO.

## 3. Áp dụng bằng with và giữ kết quả trả về

Có hai cách gọi về mặt API:

```java
Temporal result = adjuster.adjustInto(temporal);
```

và cách thường dễ đọc hơn khi biết kiểu ngày cụ thể:

```java
LocalDate result = date.with(adjuster);
```

`LocalDate.with(TemporalAdjuster)` trả về `LocalDate`, nên nơi gọi không cần tự ép kiểu từ `Temporal`. Bên trong, đối tượng ngày giờ phối hợp với quy tắc để tạo kết quả.

Với các kiểu bất biến của `java.time`, phải dùng giá trị trả về:

```java
date.with(TemporalAdjusters.lastDayOfMonth()); // Bỏ mất kết quả.
LocalDate end = date.with(TemporalAdjusters.lastDayOfMonth());
```

Lời gọi đầu tiên không cập nhật biến `date`. Cũng không cần giả định kết quả luôn là một đối tượng có địa chỉ khác: thư viện có thể trả lại một giá trị tương đương khi không cần thay đổi. Hãy quan tâm giá trị ngày giờ, dùng `equals` khi so sánh giá trị.

Hợp đồng của `TemporalAdjuster` yêu cầu không sửa đối tượng đầu vào và trả về đối tượng có cùng kiểu quan sát được. Nếu tự viết quy tắc nhận một `LocalDateTime` nhưng trả thẳng `LocalDate`, bạn đã làm mất kiểu và phần giờ thay vì điều chỉnh đúng đầu vào.

Giao diện không tự đảm bảo mọi triển khai tùy biến đều bất biến. Quy tắc phải hoạt động an toàn khi được gọi đồng thời; cách dễ giữ điều này là không lưu trạng thái thay đổi, không dùng bộ đếm chung và không thay đổi dữ liệu bên ngoài trong lúc áp dụng.

## 4. Chọn quy tắc có sẵn trước khi tự viết

Một số nhóm có sẵn trong `TemporalAdjusters`:

| Quy tắc | Ý nghĩa cần đọc đúng |
|---|---|
| `firstDayOfMonth()` | Đưa về ngày đầu tháng hiện tại |
| `lastDayOfMonth()` | Đưa về ngày cuối tháng hiện tại |
| `firstDayOfNextMonth()` | Đưa đến ngày đầu tháng kế tiếp |
| `next(dayOfWeek)` | Tìm lần xuất hiện sau ngày hiện tại, không giữ nguyên hôm nay |
| `nextOrSame(dayOfWeek)` | Giữ hôm nay nếu đã đúng thứ, nếu không thì tìm lần tiếp theo |
| `previous(...)`, `previousOrSame(...)` | Các quy tắc tương ứng theo chiều lùi |
| `firstInMonth(...)`, `lastInMonth(...)` | Tìm lần xuất hiện đầu/cuối của một thứ trong cùng tháng |

“Điều chỉnh” không nhất thiết đi về tương lai. Đưa về đầu tháng có thể lùi nhiều ngày; tìm thứ Hai tiếp theo có thể sang tháng sau. Phải đọc nghĩa của quy tắc thay vì suy ra từ việc nó được gọi qua `with`.

Nếu ngày hiện tại là thứ Hai 26/10/2026:

```text
next(MONDAY)       -> 2026-11-02
nextOrSame(MONDAY) -> 2026-10-26
```

Hai lựa chọn khác nhau ngay ở điều kiện biên. Trong bài toán hẹn lịch, cần thống nhất “thứ Hai tới” có bao gồm hôm nay hay không trước khi chọn API.

Phép cộng lượng vẫn có vai trò riêng. `plusDays(7)` luôn cộng 7 ngày; `next(MONDAY)` cộng số ngày phụ thuộc thứ của đầu vào. Viết một quy tắc để đóng gói một phép cộng đơn giản có thể hữu ích khi nó mang tên nghiệp vụ, nhưng không làm thay đổi ngữ nghĩa phép cộng ấy.

## 5. Tạo quy tắc riêng bằng ofDateAdjuster

Nếu thuật toán tự nhiên là `LocalDate` → `LocalDate`, dùng `TemporalAdjusters.ofDateAdjuster(...)` để bọc nó thành `TemporalAdjuster`.

Ví dụ quy tắc **ngày kế tiếp không phải thứ Bảy hoặc Chủ nhật**:

1. Bắt đầu từ ngày sau đầu vào, vì “kế tiếp” ở đây không bao gồm hôm nay.
2. Nếu là thứ Bảy hoặc Chủ nhật, đi tiếp một ngày.
3. Trả về ngày đầu tiên từ thứ Hai đến thứ Sáu.

Đây là quy tắc tuần đơn giản, **chưa xét ngày lễ hay lịch làm việc của tổ chức**. Không đặt tên hoặc mô tả nó như một lịch làm việc đầy đủ nếu chưa có dữ liệu ấy.

Hàm lambda trong `ofDateAdjuster` chỉ xử lý `LocalDate`. Bộ bọc sẽ áp dụng ngày kết quả trở lại đối tượng thời gian phù hợp. Vì vậy, khi dùng trên `LocalDateTime` trong ví dụ, phần ngày thay đổi còn giờ 16:45 được giữ lại.

Điều đó không có nghĩa mọi kiểu ngày giờ đều tương thích. Một `LocalTime` không có ngày để áp dụng quy tắc này. Với hệ lịch khác ISO hoặc kiểu có múi giờ, cần xác định phạm vi hỗ trợ, các trường cần thiết và chính sách liên quan; đừng suy rộng từ một ví dụ `LocalDate` sang mọi `Temporal`.

Nếu quy tắc dùng danh sách ngày nghỉ bên ngoài, hãy giữ dữ liệu đó nhất quán trong một lần tính, xác định phạm vi lịch và điều kiện kết thúc. Không âm thầm đọc “hôm nay” bên trong một quy tắc mà lẽ ra phải phụ thuộc riêng ngày đầu vào.

## 6. Thứ tự ghép và việc gọi lặp lại là một phần của hợp đồng

Hai quy tắc không nhất thiết đổi chỗ được. Với đầu vào 25/10/2026:

```text
Cuối tháng -> thứ Hai tiếp theo
2026-10-25 -> 2026-10-31 -> 2026-11-02

Thứ Hai tiếp theo -> cuối tháng
2026-10-25 -> 2026-10-26 -> 2026-10-31
```

Kết quả khác nhau vì quy tắc sau nhìn đầu vào đã được quy tắc trước biến đổi. Nếu chức năng muốn “thứ Hai cuối cùng trong tháng”, cần chọn đúng quy tắc như `lastInMonth(MONDAY)`; không thay bằng chuỗi “cuối tháng rồi thứ Hai tiếp theo”.

Cũng cần phân biệt quy tắc áp dụng lại giữ nguyên kết quả với quy tắc tiếp tục di chuyển:

- `lastDayOfMonth()` áp dụng hai lần vẫn cho cùng ngày cuối tháng.
- “Ngày kế tiếp không phải cuối tuần” áp dụng hai lần sẽ tiến thêm một ngày hợp lệ nữa.

Không mặc định mọi quy tắc điều chỉnh đều có tính lũy đẳng, tức gọi lại không đổi kết quả. Điều này đặc biệt quan trọng khi cùng một giá trị được đi qua nhiều lớp xử lý hoặc tác vụ được thử lại.

## 7. Chương trình chạy đầy đủ

Lưu đoạn sau vào `TemporalAdjusterDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài.

```java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.temporal.TemporalAdjuster;
import java.time.temporal.TemporalAdjusters;

public class TemporalAdjusterDemo {
    private static final TemporalAdjuster NEXT_WEEKDAY =
            TemporalAdjusters.ofDateAdjuster(date -> {
                LocalDate next = date.plusDays(1);
                while (next.getDayOfWeek() == DayOfWeek.SATURDAY
                        || next.getDayOfWeek() == DayOfWeek.SUNDAY) {
                    next = next.plusDays(1);
                }
                return next;
            });

    public static void main(String[] args) {
        LocalDate original = LocalDate.of(2026, 10, 25);
        LocalDate monthEnd = original.with(TemporalAdjusters.lastDayOfMonth());
        System.out.println("original=" + original);
        System.out.println("monthEnd=" + monthEnd);
        System.out.println("originalAfter=" + original);

        LocalDate monday = LocalDate.of(2026, 10, 26);
        System.out.println("nextMonday="
                + monday.with(TemporalAdjusters.next(DayOfWeek.MONDAY)));
        System.out.println("sameOrNextMonday="
                + monday.with(TemporalAdjusters.nextOrSame(DayOfWeek.MONDAY)));

        System.out.println("monthEndThenMonday="
                + original.with(TemporalAdjusters.lastDayOfMonth())
                          .with(TemporalAdjusters.next(DayOfWeek.MONDAY)));
        System.out.println("mondayThenMonthEnd="
                + original.with(TemporalAdjusters.next(DayOfWeek.MONDAY))
                          .with(TemporalAdjusters.lastDayOfMonth()));

        LocalDate friday = LocalDate.of(2026, 10, 30);
        LocalDate next = friday.with(NEXT_WEEKDAY);
        System.out.println("nextWeekday=" + next);
        System.out.println("appliedAgain=" + next.with(NEXT_WEEKDAY));

        LocalDateTime appointment = friday.atTime(16, 45);
        System.out.println("adjustedDateTime=" + appointment.with(NEXT_WEEKDAY));

        LocalDate leapMonth = LocalDate.of(2024, 2, 10);
        System.out.println("leapMonthEnd="
                + leapMonth.with(TemporalAdjusters.lastDayOfMonth()));
    }
}
```

Biên dịch và chạy:

```shell
javac TemporalAdjusterDemo.java
java TemporalAdjusterDemo
```

Kết quả chuẩn:

```text
original=2026-10-25
monthEnd=2026-10-31
originalAfter=2026-10-25
nextMonday=2026-11-02
sameOrNextMonday=2026-10-26
monthEndThenMonday=2026-11-02
mondayThenMonthEnd=2026-10-31
nextWeekday=2026-11-02
appliedAgain=2026-11-03
adjustedDateTime=2026-11-02T16:45
leapMonthEnd=2024-02-29
```

Các kết quả thể hiện các hợp đồng riêng:

- `originalAfter` chứng minh biến đầu vào không bị cập nhật bởi phép điều chỉnh trước đó.
- Hai dòng về thứ Hai cho thấy khác biệt giữa “sau hôm nay” và “hôm nay hoặc sau đó”.
- Hai dòng ghép quy tắc chứng minh thứ tự có thể đổi kết quả.
- Ngày tiếp theo sau thứ Sáu 30/10 là thứ Hai 02/11 theo quy tắc chỉ loại cuối tuần.
- Áp dụng lại quy tắc kế tiếp cho thứ Hai đưa đến thứ Ba 03/11.
- `LocalDateTime` được giữ kiểu và giờ 16:45 sau khi điều chỉnh ngày.
- Tháng 2 năm nhuận có ngày cuối tháng là 29, không cần tự viết nhánh xử lý năm nhuận.

## 8. Kiểm tra quy tắc bằng điều kiện biên

Khi dùng hoặc tự viết một `TemporalAdjuster`, hãy làm rõ:

1. Đầu vào nào được hỗ trợ: ngày ISO, ngày-giờ hay thêm những kiểu khác?
2. Có bao gồm ngày hiện tại nếu nó đã thỏa điều kiện không?
3. Kết quả được phép sang tháng/năm khác hay phải nằm trong phạm vi ban đầu?
4. Áp dụng nhiều lần có giữ nguyên hay tiếp tục dịch chuyển?
5. Có phụ thuộc ngày lễ, múi giờ, hệ lịch hoặc dữ liệu ngoài không?

Với ví dụ `NEXT_WEEKDAY`, kiểm tra thứ Năm, thứ Sáu, thứ Bảy, Chủ nhật và ngày cuối năm giúp xác nhận đúng ý nghĩa “kế tiếp”. Những giới hạn cực đại của kiểu như `LocalDate.MAX` có thể không còn ngày sau để tạo; thao tác vượt miền biểu diễn gây ngoại lệ thay vì tự quay vòng.

Không thay ngoại lệ bằng cách trả lại ngày đầu vào một cách tùy tiện. Nếu quy tắc không thực hiện được, kết quả giữ nguyên có thể khiến nơi gọi hiểu sai rằng điều kiện đã được thỏa mãn.

## 9. Tự thực hành

Đổi đầu vào của quy tắc riêng thành:

| Ngày đầu vào | Kết quả mong đợi của NEXT_WEEKDAY |
|---|---|
| `2026-10-29` (thứ Năm) | `2026-10-30` |
| `2026-10-31` (thứ Bảy) | `2026-11-02` |
| `2026-11-01` (Chủ nhật) | `2026-11-02` |
| `2026-11-02` (thứ Hai) | `2026-11-03` |

Sau đó thiết kế một quy tắc “hôm nay nếu không phải cuối tuần, nếu không thì đi tới thứ Hai”. Hãy chỉ ra khác biệt cần sửa ở bước khởi đầu so với `NEXT_WEEKDAY`, và kiểm tra lại đầu vào thứ Hai. Mục tiêu là diễn đạt rõ quy tắc trước khi viết thuật toán, không chỉ làm cho vài ngày mẫu chạy đúng.

Tham khảo: [TemporalAdjuster](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAdjuster.html) và [TemporalAdjusters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAdjusters.html) trong Java SE 21.
