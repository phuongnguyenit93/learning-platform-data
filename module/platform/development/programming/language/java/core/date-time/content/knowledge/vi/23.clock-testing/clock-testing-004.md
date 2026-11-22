# `Clock.fixed()` để cố định thời điểm kiểm thử

## 1. Cố định nguồn “hiện tại” thay vì chờ thời gian thật

Giả sử cổng đăng ký đóng từ ngày `2026-01-01` theo giờ Việt Nam. Để kiểm tra ngay trước và đúng đầu ngày đóng, không cần chờ đến giao thừa hoặc đổi đồng hồ máy. Có thể cung cấp cho phần nghiệp vụ một `Clock` mà mọi lần đọc đều trả thời điểm đã chọn.

`Clock.fixed(fixedInstant, zone)` tạo đồng hồ như vậy. Theo [Java SE 21 — Clock.fixed()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html#fixed(java.time.Instant,java.time.ZoneId)), đồng hồ luôn trả cùng một `Instant`; nó phù hợp khi cần nhìn một mốc thời gian có thể kiểm soát trong kiểm thử.

Hai đối số có vai trò khác nhau:

- `fixedInstant`: thời điểm được cố định trên dòng thời gian.
- `zone`: vùng dùng để diễn giải thời điểm ấy thành ngày, giờ địa phương khi cần.

```java
// Minh họa trong một phương thức.
Clock clock = Clock.fixed(
        Instant.parse("2025-12-31T17:00:00Z"),
        ZoneId.of("Asia/Ho_Chi_Minh"));
```

Thời điểm trên là 17:00 UTC nhưng đã là 00:00 ngày `2026-01-01` ở vùng được chọn. Đối số `zone` không cộng bảy giờ vào `Instant` được giữ bên trong; nó cung cấp ngữ cảnh để lấy ngày–giờ địa phương.

## 2. Cách đọc từ đồng hồ cố định

| Nhu cầu | Cách đọc | Kết quả có phụ thuộc vùng của clock? |
| --- | --- | --- |
| Thời điểm trên dòng thời gian | `clock.instant()` hoặc `Instant.now(clock)` | Bản thân `Instant` không đổi theo vùng |
| Ngày địa phương | `LocalDate.now(clock)` | Có |
| Giờ địa phương | `LocalTime.now(clock)` | Có |
| Ngày–giờ địa phương | `LocalDateTime.now(clock)` | Có |
| Ngày–giờ kèm vùng | `ZonedDateTime.now(clock)` | Có |

Các overload nhận `Clock` lấy nguồn giờ từ đối tượng được cung cấp. Chẳng hạn, [LocalDateTime.now(Clock)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/LocalDateTime.html#now(java.time.Clock)) tạo ngày–giờ từ đồng hồ đó; giá trị `LocalDateTime` kết quả vẫn không lưu vùng trong kiểu của nó.

Tạo một biến `Clock.fixed(...)` chưa tác động tới những chỗ vẫn gọi `Instant.now()` hoặc `LocalDate.now()` không đối số. Muốn kiểm thử kiểm soát mốc, phần mã đang kiểm tra phải nhận và sử dụng đồng hồ ấy.

## 3. Chuẩn bị một kiểm thử có ý nghĩa

Trước khi tạo clock, xác định ba điều:

1. Quy tắc đang so sánh thời điểm hay ngày địa phương?
2. Nếu theo ngày, dùng vùng nào của nghiệp vụ?
3. Mốc ranh giới có được tính trong khoảng hợp lệ hay không?

Trong ví dụ, đăng ký còn mở nếu ngày quan sát **trước** ngày đóng. Ngày đóng là `2026-01-01`; đúng từ đầu ngày ấy đã không mở nữa. Do đó chương trình kiểm tra hai mốc theo giờ Việt Nam:

| Mốc | Thời điểm UTC tương ứng | Kỳ vọng |
| --- | --- | --- |
| `2025-12-31 23:59:59.999999999` | `2025-12-31T16:59:59.999999999Z` | Còn mở |
| `2026-01-01 00:00` | `2025-12-31T17:00:00Z` | Đã đóng |

Chọn hai `Instant` cách nhau một nano giây giúp kiểm tra ranh giới chính xác trong mô hình dữ liệu. Nó không yêu cầu đồng hồ vật lý hoặc hệ điều hành thật sự có độ phân giải một nano giây.

## 4. Chương trình chạy đầy đủ

Lưu mã vào `FixedClockDemo.java`. Chương trình dùng Java 17 trở lên, không cần JUnit hay thư viện ngoài. Hàm `expect()` tự ném `AssertionError` nếu kết quả sai, nên không phụ thuộc cờ `-ea`:

```java
import java.time.*;
import java.util.Objects;

public class FixedClockDemo {
    static final class RegistrationWindow {
        private final Clock clock;

        RegistrationWindow(Clock clock) {
            this.clock = Objects.requireNonNull(clock);
        }

        boolean isOpenUntil(LocalDate closingDate) {
            LocalDate observedDate = LocalDate.now(clock);
            return observedDate.isBefore(closingDate);
        }
    }

    private static void expect(boolean expected, boolean actual, String label) {
        if (expected != actual) {
            throw new AssertionError(label + ": expected " + expected
                    + ", got " + actual);
        }
        System.out.println(label + " = " + actual);
    }

    public static void main(String[] args) {
        ZoneId businessZone = ZoneId.of("Asia/Ho_Chi_Minh");
        Instant midnight = Instant.parse("2025-12-31T17:00:00Z");
        Clock before = Clock.fixed(midnight.minusNanos(1), businessZone);
        Clock atBoundary = Clock.fixed(midnight, businessZone);

        System.out.println("before instant = " + Instant.now(before));
        System.out.println("before local = " + LocalDateTime.now(before));
        System.out.println("boundary instant = " + Instant.now(atBoundary));
        System.out.println("boundary local = " + LocalDateTime.now(atBoundary));

        LocalDate closingDate = LocalDate.of(2026, 1, 1);
        expect(true, new RegistrationWindow(before)
                .isOpenUntil(closingDate), "before closing day");
        expect(false, new RegistrationWindow(atBoundary)
                .isOpenUntil(closingDate), "at closing day");

        Clock utcView = atBoundary.withZone(ZoneOffset.UTC);
        System.out.println("UTC view date = " + LocalDate.now(utcView));
        System.out.println("original view date = " + LocalDate.now(atBoundary));
        expect(true, utcView.instant().equals(atBoundary.instant()),
                "same frozen instant");

        Instant first = before.instant();
        for (int i = 0; i < 1000; i++) {
            if (!first.equals(before.instant())) {
                throw new AssertionError("fixed clock changed");
            }
        }
        System.out.println("all fixed reads unchanged");
        System.out.println("all checks passed");
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 FixedClockDemo.java
java FixedClockDemo
```

Kết quả:

```text
before instant = 2025-12-31T16:59:59.999999999Z
before local = 2025-12-31T23:59:59.999999999
boundary instant = 2025-12-31T17:00:00Z
boundary local = 2026-01-01T00:00
before closing day = true
at closing day = false
UTC view date = 2025-12-31
original view date = 2026-01-01
same frozen instant = true
all fixed reads unchanged
all checks passed
```

Các mốc được tạo từ chuỗi cụ thể và vùng cụ thể, nên kết quả không phụ thuộc ngày chạy hoặc vùng mặc định của máy.

## 5. Đồng hồ đi vào nghiệp vụ bằng cách nào?

`RegistrationWindow` nhận `Clock` trong hàm khởi tạo, giữ trong trường `final` và gọi `LocalDate.now(clock)` trong thao tác nghiệp vụ. `Objects.requireNonNull()` giúp từ chối nguồn đồng hồ không được cung cấp ngay khi lắp đối tượng.

Khi kiểm thử, mỗi trường hợp tạo đối tượng với clock phù hợp. Thuật toán `observedDate.isBefore(closingDate)` giữ nguyên; chỉ nguồn “hôm nay” khác nhau.

Khi chạy thật, nơi khởi tạo có thể cấp đồng hồ hệ thống với vùng nghiệp vụ. Ví dụ minh họa trong phạm vi truy cập được lớp trên:

```java
RegistrationWindow production = new RegistrationWindow(
        Clock.system(ZoneId.of("Asia/Ho_Chi_Minh")));
```

Không tạo `Clock.system(...)` bên trong `isOpenUntil()` nếu mục đích thiết kế là cho nơi gọi thay nguồn thời gian. Cũng không cần một cờ `isTest` để rẽ sang dữ liệu cố định: sự khác nhau được thể hiện bằng phụ thuộc được truyền vào.

Đưa `Clock` vào không có nghĩa phải đổi mọi hàm trong ứng dụng. Có thể chỉ đặt nguồn đồng hồ ở phần dịch vụ cần “hiện tại”, còn những hàm tính toán khác nhận ngày/thời điểm đã đọc như dữ liệu thông thường.

## 6. Đổi vùng không làm clock cũ chạy hoặc đổi mốc

`atBoundary.withZone(UTC)` trả clock có cùng thời điểm nhưng cách diễn giải vùng khác. Hai clock trong chương trình cho ngày khác nhau: UTC còn là `2025-12-31`, còn vùng Việt Nam đã là `2026-01-01`.

Dòng `original view date` vẫn là ngày `2026-01-01`, cho thấy cấu hình vùng của `atBoundary` không bị sửa. `same frozen instant = true` xác nhận cả hai vẫn chỉ đến cùng một thời điểm.

Như vậy, dùng `withZone()` để chuyển cách nhìn của clock khác với tạo một clock cố định ở thời điểm khác. Nếu muốn kiểm tra ngày kế tiếp, phải chọn một `Instant` khác tương ứng với mốc muốn thử, chứ không đổi vùng tùy ý để ép kết quả ngày đổi.

Khi chọn mốc bằng ngày–giờ địa phương, có thể tạo `ZonedDateTime` với vùng rồi lấy `toInstant()` để truyền vào `Clock.fixed()`. Ở vùng có chuyển đổi giờ mùa hè, ngày–giờ đầu vào có thể rơi vào khoảng không tồn tại hoặc có hai độ lệch; phải xác định đúng mốc cần kiểm tra thay vì mặc nhiên suy ra một thời điểm duy nhất từ mọi `LocalDateTime`.

## 7. Cố định nghĩa là không tự tiến

Vòng lặp cuối đọc clock nhiều lần và luôn nhận cùng `Instant`. Ngay cả nếu chương trình chờ lâu hơn, clock cố định vẫn không trôi theo thời gian thật. Nó cũng không có phương thức “đặt lại” mốc như một đồng hồ có thể thay đổi.

Để kiểm tra trước/sau một sự kiện, cách đơn giản là dùng các clock cố định riêng như `before` và `atBoundary`. Điều này giữ mỗi trường hợp độc lập và dễ đọc. Khi thật sự cần mô phỏng một chuỗi mốc trong cùng đối tượng dịch vụ, hãy chọn thiết kế nguồn giờ có điều khiển phù hợp; không chờ bằng `Thread.sleep()` để mong `Clock.fixed()` tự tiến.

Không nhầm `Clock.systemUTC()` với đồng hồ cố định: nó dùng nguồn hệ thống đang chạy và cấu hình vùng UTC. `Clock.fixed()` giữ nguyên mốc; hai lựa chọn phục vụ hai nhu cầu khác nhau.

## 8. Giới hạn cần nhớ khi viết kiểm thử

**Clock chỉ điều khiển nơi sử dụng nó.** Đồng hồ của cơ sở dữ liệu, tác vụ theo lịch, dịch vụ ngoài hoặc mã dùng `System.currentTimeMillis()` không tự được thay thế. Một kiểm thử đi qua nhiều thành phần cần biết dấu thời gian được tạo ở đâu.

**Clock cố định không kích hoạt tác vụ.** Tạo mốc “đã đến hạn” chỉ làm những phép đọc trả mốc đó; nó không gọi bộ lập lịch hay đánh thức luồng đang đợi. Hành vi chạy công việc cần được kiểm tra qua cơ chế tương ứng.

**Cố định thời gian chưa xác nhận đúng quy tắc.** Phải kiểm tra kết quả nghiệp vụ, chẳng hạn còn mở hay đã đóng. Chỉ kiểm tra `clock.instant()` bằng mốc đã truyền vào không thay thế cho kiểm thử lớp sử dụng clock.

**Chọn clock đúng phạm vi.** Một clock cố định có thể dùng chung an toàn, nhưng không nên để các kiểm thử ghi đè biến đồng hồ toàn cục hoặc để mốc kiểm thử đi vào cấu hình chạy thật. Truyền nguồn qua đối tượng riêng cho trường hợp đang kiểm tra giúp các kịch bản không ảnh hưởng nhau.

Bài tập: thêm một trường hợp một nano giây sau `midnight`. Với cùng ngày đóng và vùng Việt Nam, kết quả vẫn phải là `false`. Sau đó giữ nguyên mốc `midnight` nhưng cấp clock UTC cho một quy tắc được định nghĩa rõ theo ngày UTC: ngày quan sát còn là `2025-12-31`, nên nó chưa đến ngày đóng `2026-01-01`. Hai kết quả khác nhau là hệ quả của hai hợp đồng vùng, không phải do `Clock.fixed()` thiếu ổn định.
