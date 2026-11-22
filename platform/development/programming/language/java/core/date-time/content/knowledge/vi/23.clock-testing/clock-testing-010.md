# `System.nanoTime()` cho đo thời gian trôi qua và giới hạn của đồng hồ hệ thống

## 1. “Bây giờ là lúc nào?” khác với “đã trôi qua bao lâu?”

Một nhật ký cần ghi sự kiện xảy ra lúc nào; một thao tác mạng cần biết đã dùng hết thời hạn chờ hay chưa. Hai câu hỏi đều liên quan thời gian nhưng cần nguồn và cách dùng khác nhau.

- Với thời điểm có thể lưu, hiển thị hoặc đối chiếu với ngày lịch, thường dùng `Instant` từ một `Clock` phù hợp.
- Với khoảng trôi qua trong cùng tiến trình JVM, dùng chênh lệch hai lần `System.nanoTime()`.

`System.nanoTime()` không trả “số nano giây kể từ năm 1970”. Nó đọc nguồn đếm thời gian độ phân giải cao của JVM, với một mốc gốc cố định nhưng tùy ý. Ý nghĩa nằm ở **hiệu hai lần đọc**, theo [Java SE 21 — System.nanoTime()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime()).

```java
// Minh họa trong một phương thức; doWork là công việc đã được định nghĩa.
long start = System.nanoTime();
doWork();
long elapsedNanos = System.nanoTime() - start;
```

Độ lớn hay dấu của riêng `start` không cho biết năm, ngày hoặc giờ. Không đưa trực tiếp nó vào `Instant.ofEpochSecond()`/`ofEpochMilli()` rồi coi kết quả là thời điểm của thao tác.

## 2. Vì sao không lấy đồng hồ lịch để thay mọi phép đo?

`System.currentTimeMillis()` gắn với mốc UTC năm 1970 và dùng đơn vị mili giây. `Instant.now()` cung cấp thời điểm hệ thống theo API ngày giờ. Chúng phù hợp cho dấu thời gian lịch, nhưng nguồn thời gian hệ thống có thể chịu tác động của việc hiệu chỉnh giờ.

Đặc tả [Java SE 21 — Instant](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/time/Instant.html) không yêu cầu mọi nguồn clock của API ngày giờ phải tiến đều, đơn điệu hoặc chính xác dưới giây. Vì vậy, không nên giả định mọi lần đọc giờ hệ thống sau đều tăng theo đúng thời gian đã trôi qua.

Ví dụ giả định một nguồn giờ lịch trả 10.000 mili giây rồi bị điều chỉnh về 9.500. Hiệu hai số là -500, dù thao tác quan sát thứ hai diễn ra sau thao tác thứ nhất. Ví dụ này chỉ mô phỏng giới hạn của cách lấy chênh lệch giờ lịch; không thực sự chỉnh đồng hồ máy.

`Duration.between(startInstant, endInstant)` vẫn tính đúng khoảng giữa **hai giá trị đã cho**. Nó không có khả năng sửa chất lượng hoặc tính đơn điệu của nguồn tạo ra hai giá trị ấy. Phép đo khoảng trôi qua và ghi dấu thời gian nên được chọn theo mục đích, thay vì đổi tên biến rồi coi các nguồn tương đương.

## 3. Cách đo và giữ đúng đơn vị

Mẫu cơ bản là lấy mốc trước công việc, lấy mốc sau, rồi trừ:

```java
static long measureNanos(Runnable action) {
    long start = System.nanoTime();
    action.run();
    return System.nanoTime() - start;
}
```

Hàm trả về số nano giây trôi qua của lần gọi hoàn thành bình thường. Nếu `action.run()` ném ngoại lệ, nó không trả kết quả đo; nếu cần ghi thời lượng cả khi thất bại, thiết kế phần ghi nhận trong `finally` nhưng vẫn giữ nguyên ý nghĩa xử lý ngoại lệ.

Kết quả tính cả thời gian thao tác phải đợi, bị ngừng để luồng khác chạy hoặc gặp hoạt động runtime trong khoảng đo. Nó không phải số thời gian CPU riêng mà luồng đã sử dụng. Những công việc bất đồng bộ cũng cần được xác định điểm kết thúc đúng: đo thời gian gửi một công việc không đồng nghĩa đo đến khi công việc đó hoàn tất.

Có thể chuyển hiệu đo thành `Duration.ofNanos(elapsedNanos)`, hoặc đổi sang đơn vị khác khi xuất. Đừng so nano giây với một hằng được hiểu là mili giây. Nếu chia số nguyên cho `1_000_000`, phần nhỏ hơn một mili giây sẽ bị bỏ trong kết quả số nguyên; điều đó không có nghĩa thao tác thực sự mất 0 nano giây.

## 4. So sánh timeout bằng hiệu, không cộng hạn rồi so mốc

Với timeout không âm, mẫu nên dùng là:

```java
if (System.nanoTime() - start >= timeoutNanos) {
    // Đã tới hoặc vượt thời hạn chờ.
}
```

Cách dễ sai là:

```java
if (System.nanoTime() >= start + timeoutNanos) {
    // Không dùng mẫu này để xử lý timeout bằng nanoTime.
}
```

Phép cộng `start + timeoutNanos` có thể tràn `long`, làm số hạn chuyển sang dấu khác và khiến phép so sánh trực tiếp sai. Khi lấy hiệu đúng cách, một lần đi qua ranh giới biểu diễn của bộ đếm vẫn cho khoảng nhỏ đúng, miễn khoảng thực đang xét nhỏ hơn `2^63` nano giây, khoảng 292 năm. Không mở rộng quy tắc này thành lời hứa xử lý mọi khoảng dài tùy ý.

Timeout cũng cần được kiểm tra miền giá trị. `Duration.toNanos()` có thể ném `ArithmeticException` khi giá trị quá lớn để biểu diễn bằng `long`. Không tự đổi số tràn thành một timeout âm hoặc một hạn đã hết.

## 5. Chương trình kiểm chứng timeout và tràn bộ đếm

Lưu mã vào `NanoTimeDemo.java`. Chương trình dùng Java 17 trở lên, không cần thư viện ngoài.

`measureNanos()` minh họa đo thực bằng `System.nanoTime()`. Phần `main` kiểm tra thuật toán timeout bằng nguồn số đếm được điều khiển, nên stdout không phụ thuộc tốc độ máy. Các số đếm giả lập có cùng đơn vị nano giây; chúng không được trình bày như kết quả đo phần cứng thật.

```java
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.LongSupplier;

public class NanoTimeDemo {
    static long measureNanos(Runnable action) {
        long start = System.nanoTime();
        action.run();
        return System.nanoTime() - start;
    }

    static final class NanoTimeout {
        private final LongSupplier source;
        private final long start;
        private final long timeoutNanos;

        NanoTimeout(Duration timeout, LongSupplier source) {
            Objects.requireNonNull(timeout);
            if (timeout.isNegative()) {
                throw new IllegalArgumentException("negative timeout");
            }
            this.timeoutNanos = timeout.toNanos();
            this.source = Objects.requireNonNull(source);
            this.start = source.getAsLong();
        }

        long elapsedNanos() {
            return source.getAsLong() - start;
        }

        boolean expired() {
            return elapsedNanos() >= timeoutNanos;
        }
    }

    private static void expect(boolean expected, boolean actual, String label) {
        if (expected != actual) {
            throw new AssertionError(label);
        }
        System.out.println(label + " = " + actual);
    }

    public static void main(String[] args) {
        AtomicLong ticks = new AtomicLong(1_000);
        NanoTimeout timer = new NanoTimeout(Duration.ofNanos(500), ticks::get);
        expect(false, timer.expired(), "initially expired");
        ticks.set(1_499);
        expect(false, timer.expired(), "before boundary");
        ticks.set(1_500);
        expect(true, timer.expired(), "at boundary");
        ticks.set(1_750);
        System.out.println("elapsed nanos = " + timer.elapsedNanos());

        long startNearWrap = Long.MAX_VALUE - 4;
        ticks.set(startNearWrap);
        NanoTimeout wrapped = new NanoTimeout(Duration.ofNanos(8), ticks::get);
        expect(false, wrapped.expired(), "near wrap initially");
        ticks.set(startNearWrap + 7);
        expect(false, wrapped.expired(), "near wrap before boundary");
        ticks.set(startNearWrap + 8);
        expect(true, wrapped.expired(), "near wrap at boundary");
        System.out.println("wrapped elapsed nanos = " + wrapped.elapsedNanos());

        long wallBefore = 10_000;
        long wallAfter = 9_500;
        System.out.println("simulated wall-clock delta = "
                + (wallAfter - wallBefore));
        System.out.println("all checks passed");
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 NanoTimeDemo.java
java NanoTimeDemo
```

Kết quả:

```text
initially expired = false
before boundary = false
at boundary = true
elapsed nanos = 750
near wrap initially = false
near wrap before boundary = false
near wrap at boundary = true
wrapped elapsed nanos = 8
simulated wall-clock delta = -500
all checks passed
```

Các kỳ vọng sai sẽ ném `AssertionError`, không phụ thuộc cờ `-ea`.

## 6. Đọc những điểm cần kiểm chứng từ ví dụ

### Trước hạn và đúng hạn là hai trường hợp riêng

Bộ đếm bắt đầu ở 1.000, timeout là 500 nano giây. Ở số đếm 1.499, hiệu là 499 nên chưa hết hạn. Ở 1.500, hiệu bằng đúng 500 nên đã hết hạn theo hợp đồng `>=`.

Khi bộ đếm là 1.750, `elapsedNanos()` trả 750. Đó là khoảng đã trôi qua, không phải thời điểm lịch. Cùng một nguồn phải được dùng cho mốc đầu và các lần đọc sau.

### Đi qua giới hạn `long` không có nghĩa thời gian đi lùi

Thí nghiệm thứ hai bắt đầu ở `Long.MAX_VALUE - 4`. Các phép cộng 7 và 8 trong mã cố ý mô phỏng bộ đếm đi qua giới hạn biểu diễn của `long`. Phép trừ với mốc đầu vẫn cho 7 hoặc 8, nên điều kiện timeout hoạt động đúng ở ranh giới.

Đây cũng là lý do không lấy dấu của giá trị `nanoTime()` làm tiêu chí lỗi. Mốc gốc là tùy ý, và giá trị riêng lẻ có thể âm. Đừng dùng `Math.abs()` lên các mốc trước khi trừ, vì như vậy sẽ phá quan hệ khoảng cách đang cần giữ.

### Kiểm thử nguồn đếm không cần `Clock.fixed()`

`NanoTimeout` nhận `LongSupplier` để đọc số đếm. Lúc chạy thật, có thể tạo đối tượng trong cùng phạm vi như sau:

```java
NanoTimeout timeout = new NanoTimeout(
        Duration.ofMillis(200), System::nanoTime);
```

Khi kiểm thử, `ticks::get` cho phép đặt số đếm trước, đúng và sau hạn mà không chờ thật. `AtomicLong` ở đây chỉ giữ số đếm để điều khiển ví dụ; chương trình không phải kiểm chứng một thuật toán lập lịch đồng thời.

`Clock.fixed()` điều khiển các phép đọc dựa trên clock ấy, không chặn hoặc thay `System.nanoTime()`. Nếu mã cần cả thời điểm lịch và khoảng trôi qua, có thể truyền hai nguồn có vai trò khác nhau thay vì giả định một clock kiểm thử sẽ điều khiển cả hai.

## 7. Độ chính xác, độ phân giải và phạm vi dùng

Đơn vị nano giây cho phép biểu diễn khoảng rất nhỏ, nhưng không có bảo đảm giá trị nguồn sẽ thay đổi sau mỗi nano giây. Hai lần đọc liên tiếp có thể bằng nhau. Đừng biến độ rộng của kiểu số hoặc tên `nanoTime` thành cam kết độ chính xác đo một nano giây trên mọi máy.

Mốc gốc chỉ có ý nghĩa nhất quán trong cùng một JVM. Không lưu số đếm tuyệt đối vào cơ sở dữ liệu để dùng sau khi ứng dụng khởi động lại, không so số đếm từ hai JVM và không gửi nó sang máy khác rồi trừ trực tiếp với số đếm nơi nhận. Nếu cần lưu sự kiện để đối chiếu giữa hệ thống, dùng dấu thời gian có hợp đồng phù hợp; nếu cần lưu thống kê thời lượng, lưu **hiệu đã tính** cùng đơn vị.

Một lần đo ngắn cũng không đủ kết luận tốc độ ổn định của một đoạn Java. Khởi động runtime, biên dịch JIT, tối ưu bỏ công việc không ảnh hưởng kết quả, bộ nhớ đệm và nhiễu lập lịch đều có thể ảnh hưởng. Phương thức `measureNanos()` là mẫu lấy hiệu, không phải một khung thử hiệu năng đầy đủ.

## 8. Giữ đúng trách nhiệm của phép đo

Đo timeout chỉ cho biết đã tới ngưỡng khi chương trình kiểm tra. Nó không tự dừng luồng, hủy lời gọi mạng hoặc bảo đảm công việc kết thúc đúng tại nano giây giới hạn. Cơ chế chờ/hủy cần được nối với quy tắc timeout theo API của thao tác đang dùng; tránh vòng lặp bận chỉ để liên tục đọc giờ.

Khi một yêu cầu thực sự nói “hết hạn tại 10:00 UTC”, đó là hạn theo thời điểm lịch và cần mô hình tương ứng. Khi yêu cầu nói “chỉ chờ tối đa 200 mili giây kể từ lúc bắt đầu”, đó là khoảng trôi qua cục bộ phù hợp với nguồn đếm của bài. Hai loại hạn có thể cùng xuất hiện trong một hệ thống nhưng không nên bị trộn số học.

Bài tập: trong phần giả lập đầu tiên, thêm số đếm 1.501; kết quả `expired()` vẫn là `true`. Sau đó đặt timeout bằng 0 và giải thích vì sao ngay lần kiểm tra đầu đã hết hạn theo quan hệ `>=`. Cuối cùng, chỉ ra vì sao thay `source.getAsLong() - start` bằng việc so mốc hiện tại với `start + timeoutNanos` sẽ làm hỏng trường hợp gần giới hạn `long` dù các ví dụ nhỏ vẫn có vẻ đúng.
