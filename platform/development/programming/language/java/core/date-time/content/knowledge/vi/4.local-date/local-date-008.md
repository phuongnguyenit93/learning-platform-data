# Kết hợp ngày với giờ bằng `LocalDate.atTime()` trong Java

Giả sử hệ thống đặt lịch lưu **ngày hẹn** là `2025-03-08` và **giờ hẹn** là `09:30`. Hai thông tin này độc lập: `LocalDate` biết ngày nhưng không biết giờ, còn `LocalTime` biết giờ trong ngày nhưng không biết đó là ngày nào. Để biểu diễn **09:30 ngày 08/03/2025**, dùng `LocalDate.atTime(...)`:

```java
LocalDate date = LocalDate.of(2025, 3, 8);
LocalTime time = LocalTime.of(9, 30);
LocalDateTime appointment = date.atTime(time);
// 2025-03-08T09:30
```

Đoạn minh họa cần `import java.time.*;` trong một phương thức Java. Kiểu kết quả là **`LocalDateTime`**: ngày + giờ trên đồng hồ địa phương, **chưa có múi giờ, offset hay thời điểm UTC**. Đây là khác biệt quan trọng khi thiết kế lịch hẹn, lịch chạy tác vụ, hạn chót và dữ liệu giao diện.

## 1. `atTime()` thực hiện chính xác điều gì?

`LocalDate.atTime(...)` kết hợp **ngày của đối tượng `LocalDate` đang gọi** với **giờ được truyền vào** để tạo một giá trị ngày-giờ mới. Không có tính toán thời gian thực đã trôi, không đọc đồng hồ hệ thống và không tự chuyển múi giờ.

Ví dụ:

| Thành phần | Kiểu | Giá trị |
| --- | --- | --- |
| Ngày lịch | `LocalDate` | `2025-03-08` |
| Giờ trong ngày | `LocalTime` | `09:30` |
| Kết quả `date.atTime(time)` | `LocalDateTime` | `2025-03-08T09:30` |

**Tính chất quan trọng:**

- Phương thức thuộc `LocalDate`, được gọi như `date.atTime(...)`; nó **không phải** phương thức trên `Instant` hoặc bộ đo thời lượng.
- Java dùng lịch ISO-8601 cho `LocalDate` và `LocalDateTime`. Kết quả chứa chính ngày, giờ, phút và các thành phần giây/nano giây đã chọn.
- Phép kết hợp không phụ thuộc `ZoneId.systemDefault()`, không đọc thời gian hiện tại và không tự phát hiện DST.
- Các lớp trong `java.time` là **bất biến**. `atTime()` trả một đối tượng khác; nó không sửa `date` hoặc `time`.
- Bản thân kết quả **không xác định một `Instant` duy nhất**. Cần gắn vùng/offset thích hợp trước khi quy đổi thành timestamp toàn cầu.

Cần phân biệt `LocalDate.atTime(...)` với `LocalDateTime.of(date, time)`: cả hai có thể tạo cùng một `LocalDateTime` từ ngày và giờ đã cho. `date.atTime(time)` thường dễ đọc khi ta **đã có sẵn `LocalDate`** và muốn thêm phần giờ.

## 2. Các dạng overload thường dùng

`LocalDate` cung cấp một số overload để tạo ngày-giờ. Hãy chọn theo cách thông tin giờ đang được biểu diễn.

| Cách gọi | Kiểu kết quả | Khi phù hợp |
| --- | --- | --- |
| `date.atTime(LocalTime.of(9, 30))` | `LocalDateTime` | Đã có một đối tượng `LocalTime` từ form, cấu hình hoặc nghiệp vụ. |
| `date.atTime(9, 30)` | `LocalDateTime` | Chỉ cần giờ và phút. Giây/nano giây mặc định bằng 0. |
| `date.atTime(9, 30, 45)` | `LocalDateTime` | Cần giờ, phút và giây. Nano giây mặc định bằng 0. |
| `date.atTime(9, 30, 45, 123_000_000)` | `LocalDateTime` | Cần thêm phần nano giây; `123_000_000` ns là 123 ms. |
| `date.atTime(OffsetTime.of(9, 30, 0, 0, ZoneOffset.ofHours(7)))` | **`OffsetDateTime`** | Giờ được cung cấp đã mang UTC offset. |

**Chú ý kiểu trả về:** overload nhận `OffsetTime` tạo **`OffsetDateTime`**, không phải `LocalDateTime`. Kết quả có offset và xác định được `Instant` bằng `toInstant()`. Offset `+07:00` vẫn **không thay thế hoàn toàn một múi giờ vùng** như `Asia/Ho_Chi_Minh`, vì vùng có các quy tắc lịch sử và có thể thay đổi theo thời gian.

Các tham số kiểu số nguyên phải hợp lệ:

- `hour`: **0–23**;
- `minute`: **0–59**;
- `second`: **0–59**;
- `nanoOfSecond`: **0–999.999.999**.

Các giá trị giờ 24, phút 60, giây 60 hoặc nano giây 1.000.000.000 không hợp lệ và có thể gây `DateTimeException`. `atTime(24, 0)` **không tự hiểu là 00:00 ngày hôm sau**. Muốn ngày kế tiếp lúc nửa đêm, viết `date.plusDays(1).atTime(LocalTime.MIDNIGHT)` và để việc đổi ngày được thể hiện rõ.

Truyền `null` cho overload cần `LocalTime` hoặc `OffsetTime` không tạo giờ mặc định; cần kiểm tra dữ liệu đầu vào. Trong trường hợp gọi trực tiếp `date.atTime(null)`, Java còn gặp vấn đề chọn overload vì có hai kiểu tham số tham chiếu `LocalTime` và `OffsetTime`; tốt nhất **không dùng `null` như giá trị giờ**.

## 3. Ví dụ đầy đủ Java 17+: kết hợp, overload, bất biến và kiểm tra đầu vào

Tạo tệp `AtTimeBasicsDemo.java` với **đúng** tên public class sau:

```java
import java.time.*;

public class AtTimeBasicsDemo {
    public static void main(String[] args) {
        LocalDate date = LocalDate.of(2025, 3, 8);
        LocalTime time = LocalTime.of(9, 30);

        LocalDateTime scheduled = date.atTime(time);

        System.out.println("Date                : " + date);
        System.out.println("Time                : " + time);
        System.out.println("atTime(LocalTime)   : " + scheduled);
        System.out.println("atTime(9, 30)       : " + date.atTime(9, 30));
        System.out.println("With seconds+nanos  : "
                + date.atTime(9, 30, 45, 123_000_000));
        System.out.println("At midnight         : "
                + date.atTime(LocalTime.MIDNIGHT));
        System.out.println("At max time         : "
                + date.atTime(LocalTime.MAX));

        OffsetTime fixedOffset = OffsetTime.of(
                9, 30, 0, 0, ZoneOffset.ofHours(7)
        );
        OffsetDateTime offsetDateTime = date.atTime(fixedOffset);

        System.out.println("At offset time      : " + offsetDateTime);
        System.out.println("As instant          : " + offsetDateTime.toInstant());
        System.out.println("Date unchanged      : " + date);

        try {
            date.atTime(24, 0);
        } catch (DateTimeException ex) {
            System.out.println("Invalid hour        : DateTimeException");
        }
    }
}
```

Biên dịch, chạy trên **JDK 17 trở lên**:

```bash
javac AtTimeBasicsDemo.java
java AtTimeBasicsDemo
```

Kết quả đã được kiểm tra bằng chạy chương trình:

```text
Date                : 2025-03-08
Time                : 09:30
atTime(LocalTime)   : 2025-03-08T09:30
atTime(9, 30)       : 2025-03-08T09:30
With seconds+nanos  : 2025-03-08T09:30:45.123
At midnight         : 2025-03-08T00:00
At max time         : 2025-03-08T23:59:59.999999999
At offset time      : 2025-03-08T09:30+07:00
As instant          : 2025-03-08T02:30:00Z
Date unchanged      : 2025-03-08
Invalid hour        : DateTimeException
```

Phân tích kết quả:

1. `date.atTime(time)` và `date.atTime(9, 30)` cho cùng giá trị `LocalDateTime`. Một cách nhận đối tượng `LocalTime`, cách kia truyền số trực tiếp.
2. `date.atTime(9, 30, 45, 123_000_000)` giữ phần giây và nano giây, hiển thị `.123` theo định dạng ISO vì chỉ cần ba chữ số phần thập phân.
3. `LocalTime.MIDNIGHT` là `00:00`. `LocalTime.MAX` là giờ cuối của ngày được biểu diễn ở độ chính xác nanosecond, tức `23:59:59.999999999`.
4. `OffsetTime` có `+07:00` tạo `OffsetDateTime` `2025-03-08T09:30+07:00`. Khi chuyển sang UTC, thời điểm là `2025-03-08T02:30:00Z` vì 09:30 trừ bảy giờ là 02:30.
5. `date` ở cuối vẫn là `2025-03-08`, xác nhận đối tượng nguồn **không bị thay đổi**.
6. `atTime(24, 0)` bị từ chối. Java không tự sửa giá trị đầu vào vượt giới hạn; ứng dụng cần xác thực dữ liệu người dùng.

## 4. Dùng `atTime()` trong thao tác nghiệp vụ

### A. Ghép dữ liệu từ biểu mẫu ngày và giờ

Một biểu mẫu đặt lịch có hai ô riêng: “Ngày” và “Giờ”. Khi người dùng gửi:

```text
Ngày : 2025-03-08
Giờ  : 09:30
```

Ta có thể parse chuỗi ISO:

```java
LocalDate appointmentDate = LocalDate.parse("2025-03-08");
LocalTime appointmentTime = LocalTime.parse("09:30");
LocalDateTime localAppointment = appointmentDate.atTime(appointmentTime);
```

Đây là **đoạn mã trong một phương thức**, cần `import java.time.*;`. Nếu nguồn là ngày/giờ định dạng Việt Nam, như `08/03/2025` và `09:30`, cần `DateTimeFormatter` có pattern phù hợp để parse ngày. Không thay đổi thông tin ngày bằng cách ghép chuỗi thủ công rồi tự suy luận vùng. Ví dụ:

```java
DateTimeFormatter dateFormatter =
        DateTimeFormatter.ofPattern("dd/MM/uuuu");
LocalDate parsedDate = LocalDate.parse("08/03/2025", dateFormatter);
LocalTime parsedTime = LocalTime.parse("09:30");
LocalDateTime parsedAppointment = parsedDate.atTime(parsedTime);
```

Đoạn trên cần thêm `import java.time.format.DateTimeFormatter;`. Sau parse, phải xác định rõ đây là **lịch tại vùng nào** nếu công việc có thực hiện ở một thời điểm cụ thể.

### B. Chọn giờ thực hiện tác vụ trong ngày

Giả sử cần gửi nhắc việc lúc 18:00 **ngày mai theo múi giờ nghiệp vụ**. Ta cần quyết định ngày hiện tại theo vùng đã chọn, rồi thêm giờ:

```java
ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
LocalDate tomorrow = LocalDate.now(businessZone).plusDays(1);
LocalDateTime nextReminderLocal = tomorrow.atTime(18, 0);
ZonedDateTime reminder = nextReminderLocal.atZone(businessZone);
Instant reminderInstant = reminder.toInstant();
```

Đây là **đoạn minh họa trong phương thức**, cần `import java.time.*;`, không có `main` độc lập. `LocalDate.now(businessZone)` tránh vô tình lấy “hôm nay” theo múi giờ của server. `atTime(18, 0)` tạo thời điểm **18:00 trên đồng hồ địa phương ngày đã chọn**; `atZone(businessZone)` mới áp quy tắc múi giờ để đổi sang `Instant`.

Nếu chức năng yêu cầu “sau đúng 24 giờ kể từ bây giờ”, thì làm việc trực tiếp với một `Instant` cộng `Duration.ofHours(24)` sẽ mô tả yêu cầu rõ hơn. `atTime()` dành cho mô hình **ngày cộng giờ địa phương**.

### C. Ngày bắt đầu/kết thúc một khoảng lọc

Khi người dùng chọn cả một ngày trên lịch, cách diễn đạt khoảng timestamp thường là từ đầu ngày đã chọn **đến trước đầu ngày kế tiếp** trong một vùng cụ thể:

```java
LocalDate selected = LocalDate.of(2025, 3, 8);
ZoneId zone = ZoneId.of("Asia/Ho_Chi_Minh");
Instant inclusiveStart = selected.atStartOfDay(zone).toInstant();
Instant exclusiveEnd = selected.plusDays(1).atStartOfDay(zone).toInstant();
```

Đây là **đoạn minh họa**, không phải lớp `main` độc lập. Dùng khoảng nửa mở `[inclusiveStart, exclusiveEnd)` tránh việc cố đoán “thời điểm cuối ngày” theo mili giây hay nano giây. `date.atTime(LocalTime.MIDNIGHT)` tạo `LocalDateTime` 00:00; `date.atStartOfDay(zone)` tìm **thời điểm bắt đầu ngày hợp lệ trong vùng**. Hai cách tiếp cận liên quan nhưng không nên coi là hoàn toàn đồng nhất ở mọi ngày/múi giờ; có vùng với thay đổi offset ngay gần nửa đêm.

## 5. Ranh giới rất quan trọng: `atTime()` chưa gắn múi giờ

`LocalDate.atTime(9, 30)` cho `2025-03-08T09:30`, **không phải** “09:30 UTC”, “09:30 Việt Nam” hay “timestamp Unix”. `LocalDateTime` chỉ biểu diễn những chữ số của ngày và giờ trên đồng hồ.

Muốn xác định giờ địa phương này ở một nơi:

```java
LocalDateTime local = LocalDate.of(2025, 3, 8).atTime(9, 30);
ZoneId vietnam = ZoneId.of("Asia/Ho_Chi_Minh");
ZonedDateTime zoned = local.atZone(vietnam);
Instant moment = zoned.toInstant();
```

Đây là **đoạn minh họa cần `import java.time.*;`**. `zoned` sẽ là `2025-03-08T09:30+07:00[Asia/Ho_Chi_Minh]`, còn `moment` là `2025-03-08T02:30:00Z`.

Một giá trị ngày/giờ địa phương có thể rơi vào **giờ bị khuyết** hoặc **giờ lặp** do DST ở các múi giờ áp dụng chuyển đổi. `atTime()` tự thân không kiểm tra quy tắc DST, vì nó chưa nhận `ZoneId`.

| Tình huống | `LocalDateTime` từ `atTime()` | Khi diễn giải bằng `ZoneId` |
| --- | --- | --- |
| Giờ địa phương bình thường | Hợp lệ | Thường có đúng một offset hợp lệ. |
| Giờ bị khuyết (*gap*) | Vẫn tạo giá trị như yêu cầu | Có thể không tồn tại thời điểm tương ứng; cần chọn chính sách xử lý. |
| Giờ bị lặp (*overlap*) | Vẫn tạo giá trị như yêu cầu | Có thể ứng với hai thời điểm khác nhau. |

### Ví dụ Java 17+: `atTime()` và giờ DST bị khuyết/lặp

Tạo tệp `AtTimeDstDemo.java`:

```java
import java.time.*;

public class AtTimeDstDemo {
    public static void main(String[] args) {
        ZoneId newYork = ZoneId.of("America/New_York");

        LocalDateTime missing =
                LocalDate.of(2024, 3, 10).atTime(2, 30);
        LocalDateTime repeated =
                LocalDate.of(2024, 11, 3).atTime(1, 30);

        System.out.println("Missing local       : " + missing);
        System.out.println("Valid offsets       : "
                + newYork.getRules().getValidOffsets(missing));
        System.out.println("Resolved gap        : " + missing.atZone(newYork));

        System.out.println("Repeated local      : " + repeated);
        System.out.println("Repeated offsets    : "
                + newYork.getRules().getValidOffsets(repeated));
        System.out.println("Default overlap     : " + repeated.atZone(newYork));
        System.out.println("Later overlap       : "
                + repeated.atZone(newYork).withLaterOffsetAtOverlap());
    }
}
```

```bash
javac AtTimeDstDemo.java
java AtTimeDstDemo
```

Kết quả đã kiểm tra:

```text
Missing local       : 2024-03-10T02:30
Valid offsets       : []
Resolved gap        : 2024-03-10T03:30-04:00[America/New_York]
Repeated local      : 2024-11-03T01:30
Repeated offsets    : [-04:00, -05:00]
Default overlap     : 2024-11-03T01:30-04:00[America/New_York]
Later overlap       : 2024-11-03T01:30-05:00[America/New_York]
```

Giải thích:

- `LocalDate.of(2024, 3, 10).atTime(2, 30)` **không ném lỗi**. Nó chỉ tạo `LocalDateTime` 02:30 ngày 10/03/2024.
- Trong `America/New_York`, 02:30 ngày này không tồn tại vì đồng hồ nhảy sang giờ mùa hè. `getValidOffsets` trả danh sách rỗng; cách xử lý mặc định của `atZone` dịch thành 03:30 theo offset `-04:00`.
- `LocalDate.of(2024, 11, 3).atTime(1, 30)` cũng tạo `LocalDateTime` bình thường. Nhưng khi vùng chuyển từ giờ mùa hè về giờ chuẩn, 01:30 xuất hiện **hai lần**, với offset `-04:00` và `-05:00`.
- `atZone` thường chọn offset trước (earlier offset) trong trường hợp overlap; `withLaterOffsetAtOverlap()` chọn offset còn lại. Hai `ZonedDateTime` có cùng chữ số ngày/giờ nhưng chỉ **hai `Instant` khác nhau**.

Nếu ứng dụng có quy tắc nghiêm ngặt (vé máy bay, bảng lương, lệnh chạy tại giờ cụ thể), hãy kiểm tra `zone.getRules().getValidOffsets(local)` và định nghĩa cách xử lý gap/overlap. Đừng giả định kết quả của `atTime()` đã được xác minh về tính tồn tại trong múi giờ.

## 6. `atTime()` so với các phương thức có vẻ gần giống

| Biểu thức | Trả về | Khác biệt |
| --- | --- | --- |
| `date.atTime(time)` | `LocalDateTime` | Ghép ngày cụ thể với giờ đã có. |
| `LocalDateTime.of(date, time)` | `LocalDateTime` | Cách viết tạo đối tượng từ hai thành phần tương đương. |
| `date.atTime(0, 0)` | `LocalDateTime` | Nửa đêm địa phương, chưa biết vùng. |
| `date.atStartOfDay()` | `LocalDateTime` | Đầu ngày không có múi giờ; thường là 00:00. |
| `date.atStartOfDay(zone)` | `ZonedDateTime` | Đầu ngày **hợp lệ sớm nhất** theo quy tắc vùng. |
| `date.atTime(offsetTime)` | `OffsetDateTime` | Kết hợp ngày với giờ đã chứa offset cố định. |
| `date.atTime(time).atZone(zone)` | `ZonedDateTime` | Diễn giải giờ địa phương theo quy tắc một vùng. |
| `date.plusDays(1).atTime(time)` | `LocalDateTime` | Chọn ngày kế tiếp rồi ghép lại giờ mong muốn. |

Không có khái niệm Java ngầm hiểu mọi `LocalDateTime` là UTC. Nếu chỉ dùng `date.atTime(...)` rồi lưu vào hệ thống phân tán, phải có hợp đồng dữ liệu xác định vùng/offset ở một nơi phù hợp; nếu không, hai máy có thể hiểu khác nhau về thời điểm được lên lịch.

## 7. Lỗi phổ biến và cách phòng tránh

1. **Gọi `atTime()` để lấy “thời điểm hiện tại”:** hàm không đọc đồng hồ. Nếu muốn thời điểm hiện tại dùng `Instant.now()`; nếu muốn ngày giờ hiện tại theo vùng dùng `LocalDateTime.now(zone)` với ý thức rằng đó vẫn chưa phải kiểu mang vùng.
2. **Tự gán UTC cho kết quả:** `2025-03-08T09:30` không thể chuyển thẳng sang thời điểm UTC nếu chưa biết vùng/offset được yêu cầu.
3. **Cho rằng hàm tự đi qua ngày khi giờ ≥ 24:** `atTime(24, 0)` là sai. Dùng `plusDays(1).atTime(0, 0)` nếu muốn nửa đêm hôm sau.
4. **Bỏ qua giới hạn số:** phút/giây từ 0 đến 59, nano giây trong 0 đến 999.999.999; parse và validate input người dùng.
5. **Nhầm phần milli giây và nano giây:** `atTime(9, 30, 45, 123)` nghĩa là 123 **nano giây**, không phải 123 ms; muốn 123 ms dùng `123_000_000`.
6. **Cho rằng thao tác thay đổi ngày gốc:** kiểu `LocalDate` bất biến. Muốn thay ngày cần gán giá trị `date = date.plusDays(1)` hoặc tạo biến mới.
7. **Bỏ qua DST khi gắn `ZoneId`:** giờ “02:30” có thể bị khuyết; giờ “01:30” có thể xuất hiện hai lần. Lỗi nằm ở diễn giải thành mốc thực, không phải ở cú pháp `atTime()`.
8. **Dùng offset cố định cho lịch lặp tại một địa điểm:** offset mô tả độ lệch UTC, không lưu toàn bộ quy tắc múi giờ vùng cho lịch tương lai.
9. **Tạo khoảng trọn ngày bằng mốc “23:59:59.999”:** dễ bỏ sót dữ liệu có độ chính xác nano giây. Nên xét khoảng nửa mở từ đầu ngày đã chọn đến đầu ngày kế tiếp.
10. **Nhầm ngày địa phương với một ngày dài 24 giờ:** cộng ngày lịch rồi `atTime(time)` giữ mục tiêu ngày và giờ đồng hồ; cộng `Duration.ofHours(24)` vào một `Instant` giữ thời lượng trôi. Qua DST hai mục tiêu có thể dẫn đến kết quả khác nhau.

## 8. Bài tập ứng dụng và đáp án

**Bài 1.** Ngày kiểm tra là `2025-06-15`, giờ bắt đầu là `08:45`. Tạo ngày-giờ bằng hai cách.

```java
LocalDate examDate = LocalDate.of(2025, 6, 15);
LocalDateTime a = examDate.atTime(8, 45);
LocalDateTime b = examDate.atTime(LocalTime.of(8, 45));
// a.equals(b) == true; cả hai là 2025-06-15T08:45
```

**Bài 2.** Một lịch hẹn từ `23:30` hôm nay đến `00:30` ngày mai. `atTime(0, 30)` trên cùng `LocalDate` có đủ chưa?

**Đáp án:** Chưa, vì nó tạo 00:30 **cùng ngày**. Phải dùng `LocalDateTime end = date.plusDays(1).atTime(0, 30);`. Nếu cần thời lượng thực giữa hai mốc, gắn vùng/offset theo nghiệp vụ rồi tính trên hai `Instant`.

**Bài 3.** Muốn ghép `2025-06-15` với `09:00+07:00` và xuất thành `Instant`, overload nào phù hợp?

**Đáp án:** Dùng `OffsetTime` rồi gọi `date.atTime(offsetTime)` để nhận `OffsetDateTime`, sau đó `toInstant()`. Nếu lịch lặp tại một thành phố thay vì offset cố định, ưu tiên giữ `ZoneId` để dùng quy tắc vùng.

**Bài 4.** Có phải mọi kết quả `date.atTime(2, 30)` đều tồn tại trong `America/New_York`?

**Đáp án:** Không. Phương thức tạo một `LocalDateTime` hợp lệ về mặt ngày/giờ, nhưng một số ngày DST không có 02:30 tại vùng đó. Phải kiểm tra quy tắc vùng trước khi ấn định thời điểm thực.

**Bài 5.** Trong phép gọi `date.atTime(9, 30, 0, 1_000_000)`, phần nano giây đại diện bao nhiêu mili giây?

**Đáp án:** 1 ms, vì 1.000.000 ns = 1 ms. Đây là một giá trị hợp lệ.

### Ghi nhớ khi sử dụng

**`LocalDate.atTime(...)` = ngày lịch đã biết + giờ trên đồng hồ → ngày-giờ địa phương.** Đối với đầu vào `LocalTime` hay các tham số số, kết quả là `LocalDateTime`; đối với đầu vào `OffsetTime`, kết quả là `OffsetDateTime`. Chỉ khi ứng dụng cung cấp thông tin offset hoặc múi giờ phù hợp thì giá trị mới có thể xác định một thời điểm trên dòng thời gian. Dùng `atTime()` khi bài toán thực sự bắt đầu từ **một ngày** và cần thêm **giờ của ngày đó**.
