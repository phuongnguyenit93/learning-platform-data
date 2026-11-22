# Tạo `TemporalAdjuster` bằng `ofDateAdjuster()`

## 1. Đóng gói một quy tắc điều chỉnh ngày

Một ứng dụng có thể nhiều lần cần quy tắc như “chuyển sang ngày làm việc kế tiếp”, “dời ngày chốt theo lịch nội bộ” hoặc “cộng hai ngày lịch”. Nếu quy tắc chỉ phụ thuộc ngày, việc viết lặp lại các nhánh xử lý tại từng nơi sẽ làm khó kiểm tra và dễ tạo những cách hiểu khác nhau.

`TemporalAdjusters.ofDateAdjuster()` biến một hàm nhận `LocalDate` và trả `LocalDate` thành một `TemporalAdjuster`. Giá trị kết quả có thể được dùng qua cú pháp quen thuộc `date.with(adjuster)`.

Theo [Java SE 21 — ofDateAdjuster()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAdjusters.html#ofDateAdjuster(java.util.function.UnaryOperator)), phương thức này giúp viết quy tắc theo ngày mà không phải tự xử lý toàn bộ giao diện `Temporal` cấp thấp. Nó không tự cung cấp lịch nghỉ hay thuật toán nghiệp vụ; phần hàm do ứng dụng truyền vào quyết định cách điều chỉnh.

Nếu yêu cầu đã có sẵn như cuối tháng hoặc thứ Sáu kế tiếp, nên dùng adjuster chuẩn tương ứng. Nếu chỉ cộng hai ngày tại một chỗ, `date.plusDays(2)` đã rõ ràng. `ofDateAdjuster()` hữu ích khi cần đặt tên, tái sử dụng hoặc truyền một quy tắc theo ngày vào các nơi khác nhau.

## 2. Hàm `LocalDate → LocalDate` được bọc như thế nào?

Kiểu hàm được nhận là `UnaryOperator<LocalDate>`: đầu vào và đầu ra đều là `LocalDate`. Lambda đơn giản có thể viết:

```java
// Minh họa trong một phương thức.
TemporalAdjuster twoDaysLater =
        TemporalAdjusters.ofDateAdjuster(date -> date.plusDays(2));
LocalDate result = LocalDate.of(2025, 6, 13).with(twoDaysLater);
```

Kết quả là `2025-06-15`. Lambda không sửa ngày đầu vào vì `LocalDate` bất biến; nó phải trả ngày kết quả.

Có thể hiểu cơ chế bọc theo ba bước:

```text
Temporal đầu vào
      ↓ lấy phần LocalDate
hàm LocalDate → LocalDate do ứng dụng cung cấp
      ↓ ngày đã điều chỉnh
áp ngày đó trở lại Temporal ban đầu
```

Bởi vậy, khi áp dụng lên `LocalDateTime`, quy tắc vẫn chỉ làm việc với ngày, không đọc giờ. Phần bọc giúp trả về đối tượng có kiểu phù hợp với đầu vào thay vì buộc mọi kết quả thành `LocalDate`.

[Java SE 21 — TemporalAdjuster](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/temporal/TemporalAdjuster.html) quy định phép điều chỉnh không sửa đầu vào và trả đối tượng cùng kiểu quan sát được. Cú pháp `temporal.with(adjuster)` thường rõ ràng hơn gọi `adjuster.adjustInto(temporal)` trực tiếp.

## 3. Xác định rõ quy tắc ngày làm việc trong ví dụ

Ta sẽ tạo quy tắc với hợp đồng sau:

1. Tìm ngày **sau** ngày đầu vào, không bao gồm chính ngày đó.
2. Thứ Bảy và Chủ nhật được coi là ngày nghỉ cuối tuần trong ví dụ.
3. Các ngày trong tập `holidays` cũng không được chọn.
4. Bộ quy tắc dùng một bản chụp tập ngày nghỉ lúc khởi tạo.

Ngày `2025-06-16` được đánh dấu nghỉ chỉ để thử nghiệm. Đây là dữ liệu giả định của bài, không phải tuyên bố về lịch nghỉ lễ chính thức. Thực tế ứng dụng phải lấy lịch phù hợp với tổ chức và phạm vi ngày cần xử lý.

Việc “sau ngày đầu vào” ảnh hưởng trực tiếp thuật toán: phải tăng một ngày ít nhất một lần rồi mới kiểm tra. Nếu ngày đầu vào đang là ngày làm việc, kết quả vẫn phải đi tới ngày làm việc tiếp theo.

## 4. Chương trình chạy đầy đủ

Lưu mã sau vào `OfDateAdjusterDemo.java`. Chương trình dùng Java 17 trở lên và không cần thư viện ngoài:

```java
import java.time.*;
import java.time.temporal.TemporalAdjuster;
import java.time.temporal.TemporalAdjusters;
import java.util.HashSet;
import java.util.Set;

public class OfDateAdjusterDemo {
    private static TemporalAdjuster nextWorkingDay(Set<LocalDate> holidays) {
        Set<LocalDate> snapshot = Set.copyOf(holidays);
        return TemporalAdjusters.ofDateAdjuster(date -> {
            LocalDate candidate = date;
            do {
                candidate = candidate.plusDays(1);
            } while (candidate.getDayOfWeek() == DayOfWeek.SATURDAY
                    || candidate.getDayOfWeek() == DayOfWeek.SUNDAY
                    || snapshot.contains(candidate));
            return candidate;
        });
    }

    public static void main(String[] args) {
        Set<LocalDate> source = new HashSet<>();
        source.add(LocalDate.of(2025, 6, 16));
        TemporalAdjuster nextWorking = nextWorkingDay(source);

        LocalDate[] dates = {
            LocalDate.of(2025, 6, 13),
            LocalDate.of(2025, 6, 14),
            LocalDate.of(2025, 6, 15),
            LocalDate.of(2025, 6, 17)
        };
        for (LocalDate date : dates) {
            System.out.println(date + " -> " + date.with(nextWorking));
        }

        source.add(LocalDate.of(2025, 6, 17));
        LocalDate original = LocalDate.of(2025, 6, 13);
        System.out.println("snapshot result = " + original.with(nextWorking));
        System.out.println("original = " + original);

        LocalDateTime meeting = original.atTime(15, 30);
        System.out.println("date-time = " + meeting.with(nextWorking));
        ZonedDateTime zoned = meeting.atZone(ZoneId.of("Asia/Ho_Chi_Minh"));
        System.out.println("zoned = " + zoned.with(nextWorking));

        try {
            YearMonth.of(2025, 6).with(nextWorking);
        } catch (DateTimeException ex) {
            System.out.println("YearMonth = DateTimeException");
        }

        TemporalAdjuster twoDaysLater =
                TemporalAdjusters.ofDateAdjuster(date -> date.plusDays(2));
        System.out.println("simple rule = " + original.with(twoDaysLater));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 OfDateAdjusterDemo.java
java OfDateAdjusterDemo
```

Kết quả:

```text
2025-06-13 -> 2025-06-17
2025-06-14 -> 2025-06-17
2025-06-15 -> 2025-06-17
2025-06-17 -> 2025-06-18
snapshot result = 2025-06-17
original = 2025-06-13
date-time = 2025-06-17T15:30
zoned = 2025-06-17T15:30+07:00[Asia/Ho_Chi_Minh]
YearMonth = DateTimeException
simple rule = 2025-06-15
```

## 5. Đọc thuật toán và kết quả

### Luôn tiến trước khi kiểm tra

Hàm nhà máy `nextWorkingDay()` trả về một adjuster, chưa tính ngày ngay khi được gọi. Mỗi lần đối tượng ngày được `.with(nextWorking)`, lambda mới nhận ngày tương ứng và bắt đầu tính.

`candidate` khởi đầu bằng ngày được truyền vào. Vòng `do ... while` tăng ngày trước, sau đó loại ngày nếu rơi vào thứ Bảy, Chủ nhật hoặc tập nghỉ. Các biến trung gian đều thuộc riêng lần gọi đó.

Từ thứ Sáu `2025-06-13`, quy tắc bỏ thứ Bảy 14, Chủ nhật 15 và thứ Hai 16 đã được đánh dấu nghỉ, nên chọn thứ Ba 17. Từ thứ Ba 17, kết quả là thứ Tư 18 vì ngày gốc không nằm trong phạm vi được chọn.

Nếu hợp đồng đổi thành “ngày làm việc đầu tiên kể từ mốc, tính cả ngày mốc”, không dùng nguyên thuật toán này. Khi đó có thể bắt đầu kiểm tra ứng viên hiện tại và chỉ tăng khi nó không hợp lệ. Hai hợp đồng phải được đặt tên và kiểm tra riêng.

### Một lần gọi không làm thay đổi đầu vào

Dòng `original = 2025-06-13` cho thấy biến đầu vào vẫn giữ ngày cũ sau khi áp dụng. Trong mã sử dụng, cần gán hoặc dùng giá trị kết quả, chẳng hạn `LocalDate dueDate = original.with(nextWorking)`.

Quy tắc “ngày làm việc kế tiếp” cũng không có tính chất áp dụng nhiều lần mà giữ nguyên. Sau một lần đã có ngày làm việc, áp dụng lần nữa sẽ đi tới ngày làm việc tiếp theo. Không dùng adjuster này như thao tác chuẩn hóa có thể chạy lại tùy ý nếu nghiệp vụ chỉ cho phép dịch ngày một lần.

### Bản chụp làm rõ ý nghĩa dữ liệu bị giữ lại

`Set.copyOf(holidays)` tạo tập không thể sửa dùng cho quy tắc. Sau khi đã tạo adjuster, chương trình thêm ngày 17 vào tập `source`; kết quả của adjuster cũ vẫn là ngày 17. Đây là hành vi đã chủ động chọn: lịch của adjuster là bản chụp lúc tạo, không phải một cửa sổ đọc trực tiếp tập nguồn đang thay đổi.

Nếu ứng dụng cập nhật lịch nghỉ, hãy tạo adjuster mới từ phiên bản lịch phù hợp hoặc thiết kế dịch vụ lịch với hợp đồng cập nhật rõ ràng. Không nên để một lambda vô tình giữ tham chiếu đến tập có thể bị sửa rồi cho cùng đầu vào các kết quả khác nhau mà người dùng mã không biết.

## 6. Dùng lại trên các kiểu thời gian khác

### Ngày–giờ có đủ phần ngày

Ví dụ `meeting.with(nextWorking)` trả `LocalDateTime` ngày 17 tháng 6 lúc 15:30. Lambda không cần được viết lại cho `LocalDateTime`; phần giờ được giữ trong ví dụ này.

Với `ZonedDateTime` thuộc `Asia/Ho_Chi_Minh`, kết quả vẫn có vùng đó và giờ 15:30 tại ngày mới. Đây là phép điều chỉnh ngày theo lịch, không phải cộng một số giây cố định.

Nếu ngày mới trong một vùng có thay đổi giờ mùa hè làm giờ địa phương không tồn tại hoặc có hai độ lệch phù hợp, việc áp lại ngày còn phải tuân theo quy tắc của kiểu có vùng. Vì vậy, không hứa rằng một quy tắc chỉ thao tác `LocalDate` sẽ tự giải quyết mọi yêu cầu về giờ, độ lệch hoặc thời gian đã trôi qua.

### Không phải mọi `Temporal` đều có một ngày đầy đủ

`YearMonth` chỉ có năm và tháng, nên không thể lấy được `LocalDate` để truyền vào lambda; ví dụ ném `DateTimeException`. Tương tự, một `LocalTime` không cung cấp ngày. `Instant` cũng không có ngày địa phương độc lập nếu chưa đặt nó trong ngữ cảnh vùng phù hợp.

Điều đó cho thấy kiểu trả về `TemporalAdjuster` không bảo đảm adjuster dùng được cho mọi lớp thời gian. Khi công khai quy tắc, hãy mô tả những kiểu/ngữ nghĩa lịch mà nó hỗ trợ. Trong bài, quy tắc được thiết kế và thử cho các ngày ISO và các giá trị ngày–giờ tương ứng.

Nếu thuật toán thật sự cần kiểm tra giờ trong ngày hoặc phải điều chỉnh nhiều trường không thuộc ngày, hãy cân nhắc một phương thức có kiểu đầu vào phù hợp hoặc một `TemporalAdjuster` riêng. Không ép mọi logic qua `ofDateAdjuster()` rồi dùng phép ép kiểu để lấy thông tin đã không được truyền vào lambda.

## 7. Viết quy tắc có thể dự đoán và dùng chung

`ofDateAdjuster()` chỉ bọc hàm. Nó không làm cho mọi trạng thái mà hàm giữ lại tự trở thành bất biến hay an toàn luồng. Lambda trong ví dụ chỉ đọc tập không thể sửa và dùng biến cục bộ, nên các lần gọi không ghi đè trạng thái tính toán của nhau.

Nếu quy tắc không phụ thuộc cấu hình thay đổi, có thể xây một lần và dùng lại qua hằng có tên rõ ràng. Nếu phụ thuộc lịch, có thể tạo một adjuster cho mỗi phiên bản lịch hoặc cấu hình đã xác định. Tránh khởi tạo lại cùng quy tắc trong từng dòng xử lý khi dữ liệu cấu hình không đổi.

Những nguyên tắc cần giữ:

- Trả về một `LocalDate` hợp lệ, không trả `null` làm dấu hiệu “không tìm thấy”. Nếu bài toán có thể không có kết quả trong một phạm vi nghiệp vụ, cần thiết kế cách báo kết quả/lỗi phù hợp với phạm vi đó.
- Không gọi `LocalDate.now()` để thay thế ngày đầu vào bên trong quy tắc; adjuster phải điều chỉnh mốc mà nơi gọi đã truyền vào.
- Không thêm việc ghi cơ sở dữ liệu, gửi thông báo hoặc thay đổi bộ đếm vào hàm tính ngày. Giữ phần tính toán có thể gọi lại và kiểm tra độc lập.
- Bảo đảm vòng tìm kiếm luôn tiến và xác định cách xử lý giới hạn ngày/phạm vi lịch. Gần `LocalDate.MAX`, phép tăng ngày có thể thất bại thay vì có kết quả tương lai.

## 8. Tự thực hành theo hợp đồng

Hãy tạo quy tắc “ngày làm việc kể từ mốc, tính cả mốc” với cùng tập nghỉ và so sánh với `nextWorkingDay()`:

| Ngày đầu vào | Bản loại ngày gốc | Bản có thể giữ ngày gốc |
| --- | --- | --- |
| `2025-06-13` — thứ Sáu | `2025-06-17` | `2025-06-13` |
| `2025-06-14` — thứ Bảy | `2025-06-17` | `2025-06-17` |
| `2025-06-16` — ngày nghỉ giả định | `2025-06-17` | `2025-06-17` |

Giữ dữ liệu nghỉ ở bản chụp ban đầu chỉ có ngày 16 khi kiểm tra bảng này. Bài tập kiểm tra phần do ứng dụng phải quyết định: có tính mốc đầu, cuối tuần nào bị loại và tập ngày nghỉ nào được sử dụng. `ofDateAdjuster()` cung cấp cách đóng gói; hợp đồng đúng phải đến từ chính quy tắc bạn viết.
