# Tại sao phải nhận lại kết quả của phép biến đổi trong `java.time`?

Trong Java, một lời gọi như `date.plusDays(1)` trông giống thao tác “cộng một ngày vào biến `date`”. Tuy nhiên, các kiểu ngày giờ chính của API hiện đại `java.time` như `LocalDate`, `LocalTime`, `LocalDateTime`, `Instant`, `OffsetDateTime` và `ZonedDateTime` là **immutable (bất biến)**: sau khi tạo đối tượng, trạng thái ngày giờ của chính đối tượng đó không bị sửa.

Vì thế, phép biến đổi **trả về giá trị kết quả**. Nếu lời gọi xong mà chương trình không sử dụng giá trị trả về, thay đổi dự kiến sẽ bị bỏ qua.

~~~java
LocalDate date = LocalDate.of(2026, 1, 31);

date.plusDays(1);                  // Có tính ra ngày 01/02, nhưng bỏ kết quả.
System.out.println(date);          // 2026-01-31

date = date.plusDays(1);           // Gán lại kết quả.
System.out.println(date);          // 2026-02-01
~~~

Đoạn trên là ví dụ đặt trong một method với `import java.time.LocalDate;`. Đây là một trong những quy tắc quan trọng nhất khi làm việc với ngày giờ Java: **lời gọi biến đổi và việc cập nhật biến là hai việc riêng biệt**.

## 1. Đối tượng bất biến nghĩa là gì?

Giả sử:

~~~java
LocalDate original = LocalDate.of(2026, 1, 31);
LocalDate tomorrow = original.plusDays(1);
~~~

Có thể hình dung:

~~~text
original ──────> LocalDate(2026-01-31)
                         |
                  plusDays(1)
                         |
                         v
tomorrow ───────> LocalDate(2026-02-01)

original vẫn tham chiếu đến ngày 31/01.
~~~

`plusDays(1)` tính ra ngày mới, rồi trả về một `LocalDate` biểu diễn ngày đó. Bản thân `original` không thay đổi. Nếu viết `original = original.plusDays(1)`, Java **gán lại biến tham chiếu** `original` để nó trỏ tới giá trị ngày mới; Java không sửa trạng thái của đối tượng ngày cũ.

Phân biệt ba khái niệm:

| Hành động | Ví dụ | Kết quả |
| --- | --- | --- |
| Tạo giá trị bất biến | `LocalDate.of(2026, 1, 31)` | Nhận đối tượng mô tả 31/01/2026 |
| Biến đổi giá trị | `date.plusDays(1)` | Trả về `LocalDate` mô tả 01/02/2026; không sửa `date` |
| Gán biến | `date = date.plusDays(1)` | Thay tham chiếu lưu trong biến `date` bằng kết quả |

Từ “trả về đối tượng mới” trong cách diễn giải thông thường là **trả về giá trị kết quả**, không phải cam kết JVM luôn cấp phát một đối tượng vật lý mới. Với thao tác không làm thay đổi giá trị, ví dụ `plusDays(0)`, triển khai có thể trả về chính đối tượng cũ. Đừng kiểm tra hành vi ngày giờ bằng toán tử `==` (đồng nhất tham chiếu); hãy dùng `equals()` để so sánh giá trị, hoặc `isBefore()`, `isAfter()`, `isEqual()` theo ngữ nghĩa kiểu thời gian tương ứng.

## 2. Vì sao API chọn thiết kế immutable?

Ngày giờ là một **giá trị**. Nếu một phương thức vô tình thay đổi ngày mà nhiều nơi đang tham chiếu cùng một đối tượng, kết quả tính lịch, đối chiếu và hiển thị có thể thay đổi ngoài ý muốn.

Thiết kế bất biến có các lợi ích thiết thực:

1. **Dễ dự đoán:** gọi phép cộng/trừ trên một giá trị không làm thay đổi dữ liệu gốc; có thể giữ cả trước và sau để so sánh.
2. **Chia sẻ an toàn hơn:** nhiều hàm hoặc luồng có thể đọc cùng đối tượng ngày giờ bất biến mà không phải khóa chỉ để ngăn sửa chính giá trị đó.
3. **Dễ kiểm thử và gỡ lỗi:** đầu vào không bị phương thức phụ trợ âm thầm sửa; phép biến đổi được thể hiện qua kết quả trả về.
4. **Dễ kết hợp phép toán:** có thể viết `date.plusDays(1).withDayOfMonth(1)` và thu được một giá trị cuối cùng rõ ràng.

Điều này không có nghĩa **mọi cấu trúc trong hệ sinh thái thời gian đều bất biến**. Ví dụ `java.time.format.DateTimeFormatterBuilder` là builder có thể thay đổi trong lúc dựng formatter. Quy tắc trong bài áp dụng cho các **kiểu giá trị ngày giờ** vừa nêu. Để so sánh, API cũ `java.util.Date` và `java.util.Calendar` có những phương thức làm thay đổi trạng thái đối tượng.

## 3. Cách sử dụng kết quả: gán lại, biến mới hoặc trả về

### Cách A: Gán lại biến khi cần tiến trạng thái tính toán

~~~java
LocalDate dueDate = LocalDate.of(2026, 1, 31);
dueDate = dueDate.plusDays(1);
dueDate = dueDate.plusWeeks(2);
~~~

Sau hai phép biến đổi, `dueDate` giữ **kết quả cuối cùng**. Không có đối tượng nào bị sửa tại chỗ; chỉ có biến `dueDate` được gán lại hai lần.

Đây là cách phù hợp khi chương trình có một biến “ngày đang xử lý”, chẳng hạn trong vòng lặp:

~~~java
LocalDate cursor = LocalDate.of(2026, 1, 1);
for (int i = 0; i < 3; i++) {
    System.out.println(cursor);
    cursor = cursor.plusDays(1); // Không gán lại sẽ in cùng một ngày.
}
~~~

### Cách B: Giữ bản gốc và dùng biến kết quả mới

~~~java
LocalDate bookingDate = LocalDate.of(2026, 1, 31);
LocalDate checkoutDate = bookingDate.plusDays(3);
~~~

Nếu nghiệp vụ cần lưu cả ngày đặt và ngày trả phòng, hãy để `bookingDate` giữ nguyên và dùng `checkoutDate`. Đây thường là cách diễn đạt rõ ràng hơn việc gán đi gán lại một biến.

### Cách C: Trả về kết quả từ phương thức

~~~java
static LocalDate extendDeadline(LocalDate current, int days) {
    return current.plusDays(days);
}
~~~

Phương thức không sửa đối tượng mà caller cung cấp. **Caller phải dùng giá trị trả về**:

~~~java
LocalDate deadline = LocalDate.of(2026, 1, 31);
deadline = extendDeadline(deadline, 3);
~~~

Nếu chỉ gọi `extendDeadline(deadline, 3);` rồi bỏ kết quả, biến của caller vẫn giữ ngày cũ.

### Cách D: Dùng kết quả trong chuỗi phép biến đổi

~~~java
LocalDate firstMonday = LocalDate.of(2026, 1, 15)
        .plusMonths(1)
        .withDayOfMonth(1)
        .with(java.time.temporal.TemporalAdjusters.nextOrSame(
                java.time.DayOfWeek.MONDAY));
~~~

Mỗi lời gọi trả về một giá trị để lời gọi tiếp theo tiếp tục biến đổi; kết quả cuối được gán cho `firstMonday`. Đoạn này minh họa phương thức chain trong Java 17+, không phải chương trình độc lập.

**Lưu ý về `final`:** khai báo `final LocalDate date = ...;` ngăn bạn gán lại biến `date`, nhưng không ngăn gọi `date.plusDays(1)`. Khi biến là `final`, hãy lưu kết quả dưới tên biến khác. `final` là ràng buộc đối với **biến tham chiếu**, còn immutable là đặc tính của **đối tượng**.

## 4. Chạy chương trình Java 17+ và kiểm tra đầu ra

Tạo tệp `ImmutableDateTimeDemo.java` với nội dung sau:

~~~java
import java.time.DayOfWeek;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.temporal.TemporalAdjusters;

public class ImmutableDateTimeDemo {
    public static void main(String[] args) {
        LocalDate payday = LocalDate.of(2026, 1, 31);

        // Lời gọi hợp lệ nhưng kết quả bị bỏ đi.
        payday.plusDays(1);
        System.out.println("no assignment = " + payday);

        // Giữ kết quả trong biến khác.
        LocalDate nextDay = payday.plusDays(1);
        System.out.println("captured = " + nextDay);
        System.out.println("source = " + payday);

        // Gán lại biến (không sửa đối tượng cũ).
        payday = payday.plusMonths(1);
        System.out.println("reassigned = " + payday);

        // with(...) cũng phải nhận kết quả.
        LocalDate monday = nextDay.with(
                TemporalAdjusters.nextOrSame(DayOfWeek.MONDAY));
        System.out.println("monday = " + monday);

        LocalDateTime meeting =
                LocalDateTime.of(2026, 1, 31, 23, 30);
        meeting.plusHours(2);
        System.out.println("meeting unchanged = " + meeting);
        meeting = meeting.plusHours(2);
        System.out.println("meeting updated = " + meeting);

        // Gán lại tham số không cập nhật biến của caller.
        LocalDate birthday = LocalDate.of(2026, 1, 15);
        shiftIgnored(birthday);
        System.out.println("after void call = " + birthday);
        birthday = shiftReturned(birthday);
        System.out.println("after return = " + birthday);
    }

    private static void shiftIgnored(LocalDate input) {
        input = input.plusDays(1);
    }

    private static LocalDate shiftReturned(LocalDate input) {
        return input.plusDays(1);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ImmutableDateTimeDemo.java
java ImmutableDateTimeDemo
~~~

Kết quả:

~~~text
no assignment = 2026-01-31
captured = 2026-02-01
source = 2026-01-31
reassigned = 2026-02-28
monday = 2026-02-02
meeting unchanged = 2026-01-31T23:30
meeting updated = 2026-02-01T01:30
after void call = 2026-01-15
after return = 2026-01-16
~~~

Những điều đáng chú ý:

- Dòng **`no assignment`** cho thấy `plusDays(1)` đã được thực thi nhưng `payday` vẫn giữ ngày 31/01.
- Dòng **`captured`** là giá trị ngày mới; dòng **`source`** xác nhận giá trị ban đầu chưa đổi.
- `plusMonths(1)` đi từ 31/01/2026 đến **28/02/2026**: kết quả có thể được **điều chỉnh thành ngày hợp lệ cuối tháng** theo quy tắc API, chứ không cố giữ ngày 31 không tồn tại.
- `with(TemporalAdjusters.nextOrSame(...))` là một phép biến đổi khác trả về ngày phù hợp: 02/02/2026.
- `LocalDateTime.plusHours(2)` cộng qua nửa đêm, nhưng `meeting` chỉ mang ngày giờ mới **sau khi gán lại**.
- `shiftIgnored` gán lại biến **tham số cục bộ**. Java truyền giá trị của tham chiếu vào phương thức; việc gán lại `input` không cập nhật biến `birthday` ở nơi gọi. Cách đúng là `return` giá trị mới rồi nhận kết quả bằng biến caller.

Kết quả các phép tính ngày và giờ trên đã được kiểm chứng bằng Java. Mã không phụ thuộc giờ hệ thống, múi giờ mặc định hay dữ liệu hiện tại nên có thể chạy lại và so sánh stdout.

## 5. Những phép biến đổi nào phải nhận giá trị trả về?

Đừng chỉ nhớ riêng `plusDays()`. Với những đối tượng ngày giờ bất biến, nhiều phương thức thường gặp đều tuân theo nguyên tắc này:

| Nhóm thao tác | Ví dụ | Kết quả phải sử dụng |
| --- | --- | --- |
| Cộng thời gian | `date.plusDays(2)`, `time.plusMinutes(15)` | Ngày/giờ sau khi cộng |
| Trừ thời gian | `date.minusMonths(1)`, `instant.minusSeconds(10)` | Ngày/giờ sau khi trừ |
| Thay trường ngày giờ | `date.withYear(2027)`, `dateTime.withHour(9)` | Giá trị có trường mới |
| Điều chỉnh theo quy tắc | `date.with(TemporalAdjusters.next(DayOfWeek.MONDAY))` | Ngày được điều chỉnh |
| Cắt độ chính xác | `time.truncatedTo(ChronoUnit.MINUTES)` | Giờ đã cắt giây/nano giây |
| Áp vùng múi giờ | `localDateTime.atZone(zone)` | `ZonedDateTime` |
| Chuyển múi giờ | `zoned.withZoneSameInstant(otherZone)` | `ZonedDateTime` ở vùng khác, cùng instant |
| Chuyển thành instant | `zoned.toInstant()` | Một `Instant` |
| Định dạng | `date.format(formatter)` | Một `String` |

Hai hàng cuối cho thấy có những thao tác **trả về kiểu dữ liệu khác**. Không thể gán `ZonedDateTime.toInstant()` về chính biến `ZonedDateTime`; thay vào đó, khai báo `Instant timestamp = zoned.toInstant();`. Tương tự, `date.format(formatter)` tạo ra **chuỗi**, không thay đổi `date` hoặc biến định dạng đầu vào.

**Đừng nhầm biến đổi với phương thức quan sát.** Những phương thức như `getYear()`, `getMonthValue()`, `isBefore()`, `equals()` chỉ đọc hoặc so sánh và trả về số/boolean; không có đối tượng ngày giờ mới cần nhận. Vấn đề không nằm ở chuyện “phương thức nào cũng phải gán lại”, mà là **khi muốn dùng kết quả tính toán, phải sử dụng giá trị được trả về**.

## 6. Chuyển múi giờ là ví dụ dễ mắc lỗi

Ngay cả khi chỉ muốn đổi cách hiển thị sang vùng khác, đối tượng cũng không tự thay đổi:

~~~java
ZonedDateTime inUtc =
        ZonedDateTime.parse("2026-01-15T09:00:00Z[UTC]");

inUtc.withZoneSameInstant(ZoneId.of("Asia/Ho_Chi_Minh"));
// inUtc vẫn biểu diễn 09:00 ở UTC.

ZonedDateTime inVietnam =
        inUtc.withZoneSameInstant(ZoneId.of("Asia/Ho_Chi_Minh"));
// inVietnam biểu diễn 16:00 ở Asia/Ho_Chi_Minh.
// inUtc vẫn biểu diễn 09:00 ở UTC.
~~~

Đây là đoạn minh họa để đặt trong method với `import java.time.ZonedDateTime;` và `import java.time.ZoneId;`. `withZoneSameInstant` **giữ nguyên instant**, thay vùng để hiển thị; kết quả phải được nhận trong `inVietnam` hoặc gán lại nếu biến cho phép.

Chú ý phân biệt `withZoneSameLocal`: phương thức đó cố **giữ nguyên giờ đồng hồ địa phương**, nên thường **thay đổi instant** và có thể phải giải quyết gap/overlap của vùng mới. Dù chọn thao tác nào, việc nhận kết quả vẫn là bắt buộc nếu muốn dùng phép biến đổi.

## 7. Lỗi thường gặp trong hàm, collection và vòng lặp

### Sai: tưởng phương thức có tác dụng phụ lên đối tượng đầu vào

~~~java
void moveBooking(LocalDate bookedDate) {
    bookedDate.plusDays(3); // Kết quả bị bỏ, caller không thấy ngày mới.
}
~~~

Nếu hàm cần trả về ngày đã dời, chữ ký nên thể hiện rõ:

~~~java
LocalDate moveBooking(LocalDate bookedDate) {
    return bookedDate.plusDays(3);
}
~~~

Nếu thiết kế chứa ngày trong một entity có setter, phải **nhận giá trị mới và gán vào thuộc tính của entity**. Ví dụ `booking.setDate(booking.getDate().plusDays(3))` cập nhật **entity có thể thay đổi**, nhưng vẫn không sửa đối tượng `LocalDate` cũ. Đây là hai lớp trạng thái khác nhau.

### Sai: dùng `forEach` mà bỏ phép biến đổi

~~~java
List<LocalDate> dates = List.of(
        LocalDate.of(2026, 1, 1),
        LocalDate.of(2026, 1, 2));

dates.forEach(d -> d.plusDays(1)); // Không tạo danh sách kết quả.

List<LocalDate> nextDates = dates.stream()
        .map(d -> d.plusDays(1))
        .toList(); // [2026-01-02, 2026-01-03]
~~~

Đoạn trên nằm trong method, cần `import java.util.List;` và `import java.time.LocalDate;`. `map` lấy giá trị trả về của lambda để dựng danh sách mới; `dates` không đổi. `Stream.toList()` khả dụng từ Java 16 và kết quả là danh sách không hỗ trợ thao tác thay đổi cấu trúc/phần tử.

Nếu thực sự muốn **thay các tham chiếu phần tử trong một `List` có thể sửa**, `replaceAll(d -> d.plusDays(1))` cập nhật danh sách. Nó không làm `LocalDate` trở thành mutable. Với `List.of(...)`, không dùng `replaceAll` để thay phần tử vì danh sách này không cho phép sửa.

### Sai: vòng lặp ngày không tiến

~~~java
LocalDate day = LocalDate.of(2026, 1, 1);
while (day.isBefore(LocalDate.of(2026, 1, 5))) {
    // Xử lý day...
    day.plusDays(1); // day không tiến: nguy cơ lặp vô hạn.
}
~~~

Cần viết `day = day.plusDays(1)`. Với vòng lặp hữu hạn, nên kiểm tra thêm điều kiện dừng và phạm vi ngày hợp lệ.

## 8. Checklist khi xem hoặc sửa code `java.time`

1. **Muốn có giá trị sau biến đổi?** Xem lời gọi `plus...`, `minus...`, `with...`, `truncatedTo`, `atZone`, `withZoneSameInstant` đã được gán, return, truyền tiếp hoặc chain chưa.
2. **Muốn giữ ngày gốc?** Dùng biến mới, ví dụ `LocalDate next = start.plusDays(1)`, và giữ `start` cho những tính toán sau.
3. **Có `final`?** Không được gán lại biến `final`; nhận kết quả dưới tên biến khác.
4. **Đang ở trong hàm?** Gán lại tham số chỉ thay tham chiếu cục bộ; cần trả kết quả hoặc cập nhật nơi lưu trạng thái theo hợp đồng API.
5. **Đang xử lý List/Stream?** `forEach` bỏ kết quả không biến đổi phần tử. Dùng `map` tạo danh sách giá trị mới hoặc `replaceAll` khi danh sách cho phép sửa.
6. **Có phép toán qua cuối tháng/cuối năm/DST?** Kiểm tra **giá trị trả về thực tế**; ngoài chuyện phải gán kết quả, phép biến đổi còn tuân thủ quy tắc ngày giờ và vùng múi giờ.
7. **Đang dùng biến `==` để kiểm tra?** Với giá trị ngày giờ, ưu tiên `equals`/các phương thức so sánh thời gian; đừng dựa vào việc API cấp phát đối tượng mới hay trả lại đối tượng cũ.
8. **Thử nghiệm đã bao gồm trường hợp bỏ kết quả?** Kiểm tra cả giá trị ban đầu và giá trị sau khi gán; đây là cách ngắn nhất để chứng minh khác biệt giữa biến đổi và mutation.

### Câu hỏi tự kiểm tra

- Gọi `date.plusDays(7);` có làm `date` đổi không? **Không.** Kết quả trả về không được dùng.
- Gọi `date = date.plusDays(7);` có sửa đối tượng ngày cũ không? **Không.** Biến `date` được gán tham chiếu tới giá trị mới.
- `LocalDate a = date; LocalDate b = a.plusDays(1);` thì `date` có đổi không? **Không.** `a` và `date` vẫn tham chiếu giá trị ban đầu.
- Trong một phương thức `void`, gán lại tham số kiểu `LocalDate` có cập nhật biến người gọi không? **Không.** Phải trả về kết quả hoặc sửa trạng thái của một đối tượng chứa dữ liệu (nếu hợp đồng cho phép).
- `date.plusDays(0)` có bắt buộc trả về tham chiếu khác `date` không? **Không.** Quan tâm giá trị, không dựa vào identity của đối tượng.
- `date.format(formatter)` có thay đổi `date` không? **Không.** Nó trả về một `String`.

**Ghi nhớ:** Các kiểu giá trị ngày giờ hiện đại của Java được thiết kế bất biến. Những lời gọi như `plusDays()`, `minusHours()`, `with...` và `withZoneSameInstant()` là **phép tính tạo ra kết quả**. Chỉ khi **gán lại, truyền tiếp, trả về hoặc sử dụng kết quả**, chương trình mới quan sát được phép biến đổi mong muốn.