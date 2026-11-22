# Clock.offset() và Clock.tick()

## 1. Hai cách biến đổi cách đọc thời gian

Khi kiểm thử một chức năng phụ thuộc “bây giờ”, có lúc cần nhìn thời gian muộn hơn nguồn gốc 90 phút. Có lúc lại muốn nguồn chỉ bộc lộ các mốc tròn giây, không có phần lẻ nano giây.

`Clock.offset` và `Clock.tick` đáp ứng hai nhu cầu khác nhau:

| Phương thức | Tác động lên thời điểm từ đồng hồ nền | Ví dụ |
|---|---|---|
| `Clock.offset(base, duration)` | Cộng một lượng thời gian cố định | Lệch về tương lai 90 phút |
| `Clock.tick(base, duration)` | Cắt xuống mốc của bước thời gian được chọn | Chỉ đọc mốc tròn giây |

Cả hai trả về một `Clock`, nên có thể truyền tiếp vào `Instant.now(clock)`, `LocalDate.now(clock)` hoặc một lớp đã nhận đồng hồ. Chúng không sửa giờ máy tính và không tự thay đồng hồ của các phần mã vẫn gọi `now()` không tham số.

## 2. Clock.offset: thêm độ dịch cố định vào nguồn

Cú pháp:

```java
Clock shifted = Clock.offset(base, Duration.ofMinutes(90));
```

Đây là khai báo minh họa với biến `base` đã có. Mỗi lần đọc đồng hồ kết quả, thời điểm được lấy từ đồng hồ nền rồi cộng độ dịch.

Nếu nền trả `2026-10-25T12:34:56Z`, độ dịch +90 phút cho `2026-10-25T14:04:56Z`. Độ dịch âm 5 phút cho `2026-10-25T12:29:56Z`.

Các tính chất cần nhớ:

- `Duration` có thể dương, âm hoặc bằng 0.
- Độ dịch bằng 0 không làm thay đổi kết quả và API có thể trả lại đồng hồ nền.
- Múi giờ của đồng hồ lệch được giữ từ đồng hồ nền.
- Đồng hồ gốc không bị cập nhật bởi việc tạo đồng hồ lệch.
- Nền chạy theo hệ thống thì nguồn lệch cũng đi theo nền; nền cố định thì kết quả sau dịch cũng cố định.

### Offset của Clock không phải ZoneOffset

`Clock.offset` thay đổi **thời điểm được báo**. `withZone` thay đổi **múi giờ dùng để diễn giải thời điểm** mà không chủ động cộng một lượng vào trục thời gian.

Cộng 7 giờ bằng `Clock.offset` không phải cách chuyển cùng một thời điểm sang giờ Việt Nam: nó đang tạo một thời điểm khác. Nếu cần ngày/giờ Việt Nam tại cùng thời điểm, dùng `ZoneId` phù hợp và chuyển đổi qua múi giờ.

Tương tự, `Duration.ofDays(1)` là 24 giờ theo lượng thời gian, không phải quy tắc “cùng giờ địa phương ngày mai” ở mọi múi giờ có DST. Khi yêu cầu theo ngày lịch, cần tính trên kiểu và múi giờ thích hợp thay vì dùng offset để ngầm thay thế.

### Không phải lệnh điều khiển “đi nhanh hơn”

Một độ dịch +90 phút không làm đồng hồ chạy với tốc độ gấp đôi. Nó chỉ giữ một khoảng lệch so với nền. Việc gọi `offset` cũng không làm nền tự tiến tới mốc mới.

Nếu muốn kiểm thử một chức năng ở nhiều mốc, có thể tạo các đồng hồ dựa trên cùng nguồn cố định rồi truyền lần lượt. Không cần chờ ngoài đời 90 phút để thấy kết quả tương lai.

## 3. Clock.tick: cắt độ phân giải quan sát được

Ví dụ:

```java
Clock wholeSeconds = Clock.tick(base, Duration.ofSeconds(1));
```

Với nguồn `12:34:56.789123456Z`, kết quả là `12:34:56Z`. Đây là **cắt xuống**, không làm tròn đến mốc gần nhất theo khoảng cách: dù phần lẻ gần giây 57 hơn, kết quả vẫn ở đầu giây 56.

| Nguồn nền | Bước tick | Kết quả |
|---|---|---|
| `12:34:56.789123456Z` | 1 giây | `12:34:56Z` |
| `12:34:56.789123456Z` | 250 mili giây | `12:34:56.750Z` |
| `12:34:56.789123456Z` | 1 phút | `12:34:00Z` |

Nhiều lần đọc trong cùng một khoảng tick có thể trả cùng giá trị. Điều đó là mục đích của đồng hồ này, không tự là lỗi nguồn thời gian bị đứng.

Mốc tick gắn với cách cắt thời điểm, không bắt đầu tại lúc bạn tạo đối tượng. Tạo đồng hồ lúc giây 56.789 với bước 1 giây không có nghĩa các lần nhảy sau sẽ là 57.789, 58.789.

### Không phải bộ lập lịch

`tick` không tạo luồng nền để chạy một tác vụ mỗi giây, không gọi callback và không `sleep` chờ tới mốc sau. Nó chỉ cung cấp một cách đọc thời điểm có bước quan sát lớn hơn.

Nếu nền là `Clock.fixed`, bọc thêm `tick` vẫn không làm nguồn tự tiến lên. Mỗi lần hỏi cùng một nền cố định, bạn vẫn nhận mốc bị cắt của cùng thời điểm đó.

Muốn lập lịch tác vụ cần công cụ lập lịch; muốn kiểm thử một chuỗi mốc thời gian cần nguồn thay đổi có kiểm soát hoặc nhiều đồng hồ cố định. Không dùng `tick` rồi chờ rằng số lần gọi `instant()` sẽ làm thời gian tăng thêm một bước.

## 4. Chọn tickDuration hợp lệ

Không phải mọi độ dài nano giây đều được chấp nhận. Theo hợp đồng `Clock.tick`:

- Khoảng âm bị từ chối bằng `IllegalArgumentException`.
- Khoảng bằng 0 hoặc 1 nano giây không có tác dụng cắt; trả về đồng hồ nền theo hợp đồng API.
- Các bội nguyên của mili giây, như 1 ms, 250 ms, 1 giây hoặc 1 phút, là những lựa chọn thông dụng hợp lệ.
- Nếu khoảng có phần nhỏ hơn một mili giây, độ dài của nó phải chia hết một giây theo số nano giây, không để dư. Ví dụ 20 ns hoặc 500.000 ns thỏa điều kiện; 3 ns không thỏa.

Khoảng quá lớn cũng có thể gây `ArithmeticException` khi không biểu diễn được theo số nano giây cần thiết. Chọn khoảng theo nhu cầu thực tế và xử lý cấu hình sai ở nơi dựng nguồn thời gian.

Có các phương thức tiện ích dùng nguồn hệ thống:

```java
Clock seconds = Clock.tickSeconds(zone);
Clock minutes = Clock.tickMinutes(zone);
Clock millis = Clock.tickMillis(zone);
```

Các đoạn này giả định `zone` là `ZoneId` đã được chọn. Chúng thuận tiện cho nguồn hệ thống; khi kiểm thử muốn giữ nguồn nền cụ thể, dùng `tick(base, duration)` để không vô tình quay về đọc giờ thật.

## 5. Thứ tự offset và tick có thể đổi kết quả

Hai phép biến đổi không phải lúc nào đổi chỗ được. Với nền `12:34:56.789123456Z`, độ dịch 1,5 giây và bước tick 1 giây:

```text
offset rồi tick:
12:34:56.789123456
    + 1,5 giây -> 12:34:58.289123456
    cắt giây   -> 12:34:58

tick rồi offset:
12:34:56.789123456
    cắt giây   -> 12:34:56
    + 1,5 giây -> 12:34:57.500
```

Nếu hợp đồng yêu cầu đầu ra luôn tròn giây, áp dụng offset **sau** tick có thể đưa phần lẻ trở lại. Đặt tên hoặc viết cấu trúc lồng rõ ràng để thể hiện quy tắc cuối cùng.

Không dùng việc hai thứ tự tình cờ cho cùng kết quả với offset nguyên giây làm bằng chứng rằng chúng luôn tương đương. Phép kiểm tra nên có độ dịch không phải bội của bước tick.

## 6. Chương trình chạy đầy đủ

Lưu mã sau vào `OffsetAndTickDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài. Toàn bộ nguồn nền được cố định nên kết quả không phụ thuộc lúc chạy.

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

public class OffsetAndTickDemo {
    public static void main(String[] args) {
        Clock base = Clock.fixed(
                Instant.parse("2026-10-25T12:34:56.789123456Z"),
                ZoneOffset.UTC);

        System.out.println("base=" + base.instant());
        System.out.println("plus90Minutes="
                + Clock.offset(base, Duration.ofMinutes(90)).instant());
        System.out.println("minus5Minutes="
                + Clock.offset(base, Duration.ofMinutes(-5)).instant());
        System.out.println("offsetZone="
                + Clock.offset(base, Duration.ofHours(1)).getZone());

        Clock seconds = Clock.tick(base, Duration.ofSeconds(1));
        System.out.println("tickSecond=" + seconds.instant());
        System.out.println("tick250ms="
                + Clock.tick(base, Duration.ofMillis(250)).instant());
        System.out.println("tickMinute="
                + Clock.tick(base, Duration.ofMinutes(1)).instant());
        System.out.println("tickSecondAgain=" + seconds.instant());

        Duration shift = Duration.ofMillis(1500);
        Clock offsetThenTick = Clock.tick(
                Clock.offset(base, shift), Duration.ofSeconds(1));
        Clock tickThenOffset = Clock.offset(
                Clock.tick(base, Duration.ofSeconds(1)), shift);
        System.out.println("offsetThenTick=" + offsetThenTick.instant());
        System.out.println("tickThenOffset=" + tickThenOffset.instant());

        for (String text : new String[]{
                "2026-10-25T12:34:56.100Z",
                "2026-10-25T12:34:56.999999999Z",
                "2026-10-25T12:34:57Z"
        }) {
            Clock sample = Clock.fixed(Instant.parse(text), ZoneOffset.UTC);
            System.out.println("boundary=" + Clock.tick(
                    sample, Duration.ofSeconds(1)).instant());
        }

        System.out.println("zeroTick="
                + Clock.tick(base, Duration.ZERO).instant());
        System.out.println("oneNanoTick="
                + Clock.tick(base, Duration.ofNanos(1)).instant());

        try {
            Clock.tick(base, Duration.ofNanos(3));
        } catch (IllegalArgumentException e) {
            System.out.println("invalid3ns=IllegalArgumentException");
        }
        try {
            Clock.tick(base, Duration.ofSeconds(-1));
        } catch (IllegalArgumentException e) {
            System.out.println("negativeTick=IllegalArgumentException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac OffsetAndTickDemo.java
java OffsetAndTickDemo
```

Kết quả chuẩn:

```text
base=2026-10-25T12:34:56.789123456Z
plus90Minutes=2026-10-25T14:04:56.789123456Z
minus5Minutes=2026-10-25T12:29:56.789123456Z
offsetZone=Z
tickSecond=2026-10-25T12:34:56Z
tick250ms=2026-10-25T12:34:56.750Z
tickMinute=2026-10-25T12:34:00Z
tickSecondAgain=2026-10-25T12:34:56Z
offsetThenTick=2026-10-25T12:34:58Z
tickThenOffset=2026-10-25T12:34:57.500Z
boundary=2026-10-25T12:34:56Z
boundary=2026-10-25T12:34:56Z
boundary=2026-10-25T12:34:57Z
zeroTick=2026-10-25T12:34:56.789123456Z
oneNanoTick=2026-10-25T12:34:56.789123456Z
invalid3ns=IllegalArgumentException
negativeTick=IllegalArgumentException
```

Các dòng `boundary` dùng ba nguồn cố định riêng, không phải một đồng hồ được tự động tăng:

1. Giây 56.100 bị cắt về đầu giây 56.
2. Ngay trước giây 57 vẫn trả đầu giây 56.
3. Đúng đầu giây 57 thì trả giây 57.

Dòng `tickSecondAgain` lặp lại cùng giá trị vì nền không thay đổi. Dòng `offsetZone=Z` xác nhận offset một giờ không biến múi giờ UTC thành `+01:00`.

Tên ngoại lệ ở các dòng cuối là nhãn do chương trình in khi bắt cấu hình không hợp lệ, không phải toàn bộ thông điệp của JDK.

## 7. Giới hạn khi dùng với nguồn hệ thống

### Tick không làm nguồn chính xác hơn

Nếu đồng hồ nền bị sai hoặc bị hiệu chỉnh, tick chỉ biến đổi giá trị được cung cấp. Nó không đồng bộ giờ và không tạo đảm bảo đơn điệu rằng các lần đọc luôn tăng. Offset cũng chỉ thêm một khoảng lệch, không chữa nguyên nhân của nguồn sai.

Các triển khai tick có thể dùng bộ nhớ đệm để tối ưu. Mốc thay đổi quan sát qua đồng hồ tick có thể xuất hiện trễ hơn so với đọc nguồn nền trực tiếp. Không xây kiểm thử thời gian thực dựa trên giả định ranh giới tick luôn được nhìn thấy chính xác ngay tức khắc.

### Giảm độ phân giải có thể ảnh hưởng điều kiện hết hạn

Nếu một phép kiểm tra cần thời điểm chính xác nhưng nguồn bị cắt theo phút, nó có thể tiếp tục nhìn một mốc cũ trong suốt phút đó. Chọn tick như một phần của hợp đồng thời gian, không chỉ là cách làm chuỗi in ra đẹp hơn.

Nếu chỉ muốn hiển thị không có phần lẻ, có thể dùng bộ định dạng ở biên hiển thị mà vẫn giữ `Instant` đầy đủ cho thuật toán. Giảm độ phân giải của nguồn là một quyết định rộng hơn việc đổi cách in.

### Lần đọc riêng vẫn là những lần đọc riêng

Với nguồn chạy thật, đọc base rồi đọc offset hoặc tick sau đó có thể có thêm thời gian trôi giữa hai lời gọi. Không kiểm tra chênh lệch luôn đúng từng nano giây bằng hai lần đọc liên tiếp. Dùng nguồn cố định khi xác nhận công thức biến đổi, như chương trình ở trên.

## 8. Tự thực hành

1. Đổi độ dịch trong phần ghép từ 1.500 ms sang 1.000 ms. Quan sát hai thứ tự cho cùng kết quả trong trường hợp này, rồi giải thích vì sao nó không phủ định ví dụ độ dịch 1,5 giây.
2. Đổi phần lẻ của nguồn thành `.249999999` và `.250000000`, giữ bước 250 ms. So sánh hai mốc cắt ngay trước và đúng ranh giới.
3. Giữ nguồn cố định rồi gọi tick nhiều lần. Xác nhận số lần gọi không làm mốc tiến lên; loại bỏ suy nghĩ tick là bộ đếm bước của kiểm thử.
4. Tạo một đồng hồ offset +24 giờ và so sánh với việc chỉ gọi `withZone` trên nguồn gốc. Chỉ ra phép nào thay đổi `Instant`, phép nào thay đổi cách xác định ngày/giờ địa phương.

Tham khảo: [Clock — offset, tick và các phương thức tiện ích](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Clock.html) trong Java SE 21.
