# Phân biệt nanoTime với đồng hồ ngày giờ

## 1. Hai câu hỏi khác nhau cần hai nguồn thời gian

Trong đo hiệu năng JVM, trước hết cần xác định câu hỏi:

- **“Đã trôi qua bao lâu?”**: đo một khoảng thời gian giữa hai mốc trong cùng lần chạy JVM, thường dùng `System.nanoTime()`.
- **“Sự kiện xảy ra lúc nào?”**: ghi một thời điểm có thể hiểu theo lịch, thường dùng `Instant.now()`, `Clock` hoặc giá trị epoch từ `System.currentTimeMillis()`.

Một tác vụ có thể bắt đầu lúc `2026-10-30T00:00:00Z` và mất 12 mili giây. Giá trị đầu là dấu thời gian của sự kiện; giá trị sau là khoảng thời gian. Chúng phục vụ những mục đích khác nhau, dù đều có thể được biểu diễn bằng con số.

| Nhu cầu | Lựa chọn định hướng |
| --- | --- |
| Đo độ trễ của lời gọi trong một JVM đang chạy | Hiệu của hai lần `System.nanoTime()` |
| Kiểm tra ngân sách timeout cục bộ | Khoảng đã trôi qua từ nguồn `nanoTime` |
| Ghi lúc tạo đơn hàng hoặc lúc nhận yêu cầu | `Instant` từ đồng hồ ngày giờ |
| Hiển thị ngày/giờ cho người dùng | Chuyển thời điểm sang múi giờ phù hợp |
| Quy tắc hết hạn theo một thời điểm lịch đã lưu | So sánh thời điểm bằng nguồn ngày giờ được kiểm soát |

Không chọn `nanoTime()` chỉ vì tên có “nano”. Tính chất và mốc tham chiếu của nguồn thời gian quan trọng hơn đơn vị hiển thị.

## 2. nanoTime không phải số nano giây từ năm 1970

`System.nanoTime()` trả giá trị của nguồn thời gian độ phân giải cao của JVM. Mốc gốc là một mốc cố định nhưng tùy ý; giá trị có thể âm. Các lần gọi trong cùng một JVM dùng cùng mốc, còn JVM khác có thể dùng mốc khác. Ý nghĩa chủ yếu nằm ở **hiệu giữa hai giá trị cùng nguồn**, không phải giá trị thô. [API System.nanoTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime()).

Do đó, các cách diễn giải sau không hợp lệ:

```java
long tick = System.nanoTime();
// Sai về ý nghĩa: tick không phải epoch-nanoseconds.
Instant wrong = Instant.ofEpochSecond(0, tick);
```

Đoạn này minh họa lỗi mô hình, không phải cách dùng được khuyến nghị. Kết quả có thể trông giống một ngày giờ hợp lệ nhưng không đại diện thời điểm hiện tại.

Cũng không thể xem giá trị `nanoTime()` là thời gian JVM đã chạy kể từ lúc khởi động. Nó không có hợp đồng rằng mốc 0 là thời điểm khởi động JVM. Nếu cần uptime, chọn API quản lý JVM phù hợp thay vì suy luận từ tick thô.

### Dùng được giữa các luồng, nhưng phải truyền dữ liệu đúng

Hai mốc trong cùng JVM có thể được lấy ở hai luồng khác nhau. Tuy nhiên, thời gian không thay thế cơ chế đồng bộ: cần truyền mốc bắt đầu và kết quả qua phương thức, future, hàng đợi hoặc cấu trúc có quy tắc hiển thị bộ nhớ phù hợp. Một lệnh đọc đồng hồ không tự tạo quan hệ đồng bộ giữa các luồng.

## 3. Đồng hồ ngày giờ có quan hệ với trục thời gian lịch

`System.currentTimeMillis()` trả số mili giây từ epoch `1970-01-01T00:00:00Z`. `Instant` biểu diễn một thời điểm trên trục thời gian; phù hợp ghi dấu sự kiện và lưu trữ dữ liệu thời gian. Múi giờ được áp dụng khi diễn giải/hiển thị thời điểm thành ngày giờ địa phương. [API System.currentTimeMillis](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#currentTimeMillis()), [API Instant](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Instant.html).

Đồng hồ ngày giờ có thể chịu hiệu chỉnh của hệ điều hành hoặc nguồn đồng bộ thời gian. Không có bảo đảm chung rằng mọi lần `Instant.now()` đều tăng đều hoặc tăng nghiêm ngặt. Đổi sang `Instant` cũng không tự biến nguồn ngày giờ thành nguồn đo khoảng thời gian đơn điệu.

Một tình huống tự thiết kế:

```text
Lúc bắt đầu: đồng hồ ngày giờ báo 10:00:00
Tác vụ chạy một khoảng ngắn
Trong lúc đó đồng hồ được chỉnh lùi 1 phút
Lúc kết thúc: đồng hồ báo 09:59:01
Lấy giờ kết thúc trừ giờ bắt đầu -> một khoảng âm
```

Khoảng âm ấy không chứng minh tác vụ “chạy ngược thời gian”. Nó cho thấy đã dùng nguồn phục vụ ngày giờ để trả lời một câu hỏi về thời gian trôi qua trong khi nguồn bị hiệu chỉnh.

Điều chỉnh múi giờ hiển thị và điều chỉnh nguồn giờ hệ thống cũng là hai việc khác nhau. Một `Instant` không đổi chỉ vì người dùng chọn múi giờ khác; cách trình bày ngày giờ của nó mới thay đổi.

## 4. Đo khoảng đã trôi qua bằng phép trừ hai mốc

Mẫu đo cơ bản:

```java
long started = System.nanoTime();
try {
    action.run();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    Duration elapsed = Duration.ofNanos(elapsedNanos);
    recordDuration(elapsed);
}
```

Đây là đoạn tích hợp minh họa: `action` là `Runnable`; `recordDuration` do ứng dụng cung cấp; cần import `java.time.Duration`. Trong mã thật, bộ ghi nhận nên tránh làm che mất lỗi gốc nếu `action` thất bại.

Phần đo bao gồm những gì nằm giữa hai mốc: thời gian chạy mã, chờ khóa, chờ I/O, bị hệ điều hành ngừng cấp CPU hoặc bị tác động bởi hoạt động JVM trong khoảng ấy. Đây là thời gian trôi qua mà người gọi quan sát, không phải chỉ số thời gian CPU thuần.

Nếu thao tác trả về một future ngay lập tức, lấy mốc sau lời gọi đó chỉ đo thời gian trả về future. Muốn đo đến khi công việc bất đồng bộ hoàn tất, cần lấy mốc kết thúc tại điểm hoàn tất tương ứng và giữ nguyên mốc bắt đầu.

Không lấy một mốc bằng `currentTimeMillis()` rồi trừ một mốc bằng `nanoTime()`, kể cả đã nhân/chia cho cùng đơn vị. Cùng đơn vị không làm hai mốc gốc khác nhau trở thành tương thích.

## 5. Độ chính xác biểu diễn không phải độ phân giải thực tế

Giá trị `nanoTime()` được biểu diễn bằng nano giây, nhưng API không bảo đảm nguồn thay đổi sau đúng mỗi nano giây. Hai lần gọi gần nhau có thể trả cùng giá trị. Sai số và chi phí đọc đồng hồ cũng cần được xét khi đo công việc rất ngắn. [API nanoTime](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime()).

Có thể tách ba ý:

| Khái niệm | Câu hỏi |
| --- | --- |
| Đơn vị/độ chính xác biểu diễn | Con số được ghi theo nano giây hay mili giây? |
| Độ phân giải | Nguồn có thể phân biệt các khoảng nhỏ đến mức nào? |
| Độ chính xác so với thực tế | Kết quả gần khoảng thời gian thật đến đâu? |

Nhân số mili giây với `1_000_000` chỉ đổi đơn vị, không tạo thêm thông tin. Tương tự, một `Instant` có phần nano giây không chứng minh đồng hồ tạo ra nó chính xác đến nano giây.

Vì vậy, một phép đo bằng 0 không nhất thiết nghĩa là thao tác không tốn thời gian. Nó có thể quá ngắn so với độ phân giải hoặc thiết kế phép đo không đủ phù hợp.

## 6. Timeout: trừ trước rồi so sánh

Để kiểm tra đã dùng hết ngân sách chưa, mẫu định hướng là:

```java
boolean expired = System.nanoTime() - started >= timeoutNanos;
```

Tránh biến nó thành phép so sánh trực tiếp với tổng có thể tràn:

```java
// Không dùng mẫu này làm kiểm tra timeout tổng quát.
boolean unsafe = System.nanoTime() >= started + timeoutNanos;
```

`long` có giới hạn. Giá trị nguồn có thể qua biên từ dương sang âm; so sánh thứ tự trực tiếp của hai tick không còn diễn đạt thứ tự thời gian như mong muốn. Phép trừ theo mẫu API xử lý được việc đi qua biên khi khoảng cần đo còn trong miền hợp lệ. Khoảng hai mốc phải nhỏ hơn `2^63` nano giây, xấp xỉ 292 năm; ngân sách cũng phải có miền và đơn vị rõ ràng. [API nanoTime và ví dụ timeout](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/System.html#nanoTime()).

Không cần đợi 292 năm mới gặp lỗi của phép cộng deadline: mốc gốc tùy ý có thể đã gần biên kiểu số. Bài kiểm tra mô phỏng giá trị gần biên có thể phát hiện sai ngay lập tức.

### Timeout kiểm tra khác với bộ lập lịch

Một biểu thức `expired` chỉ cho biết tình trạng tại lúc kiểm tra. Nó không tự ngắt tác vụ hoặc bảo đảm một luồng được đánh thức đúng hạn. Nếu thao tác chặn không bao giờ trả về, mã kiểm tra phía sau cũng không được chạy.

Trong ứng dụng, ưu tiên API có timeout/hủy tương ứng với loại công việc và quản lý ngân sách còn lại giữa các bước. Không tạo vòng lặp bận chỉ để liên tục đọc `nanoTime()`.

## 7. Chương trình Java 17+: tách mốc lịch và tick đo khoảng

Chương trình sau dùng đồng hồ lịch cố định và dữ liệu tick **giả lập**. Nó không thay đồng hồ hệ điều hành và không chờ thời gian thực. Mục đích là kiểm tra hai tính chất độc lập: giờ lịch có thể được dịch lùi trong mô hình kiểm thử; hiệu tick vẫn tính được qua biên `long` với khoảng nhỏ.

Lưu thành `ClockKindsDemo.java`:

```java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;

public class ClockKindsDemo {
    static boolean expired(long startTick, long nowTick, long budgetNanos) {
        if (budgetNanos < 0) {
            throw new IllegalArgumentException("Negative budget");
        }
        return nowTick - startTick >= budgetNanos;
    }

    public static void main(String[] args) {
        Clock wall = Clock.fixed(
                Instant.parse("2026-10-30T00:00:00Z"), ZoneOffset.UTC);
        Clock movedBack = Clock.offset(wall, Duration.ofMinutes(-1));
        long wallDelta = Duration.between(wall.instant(), movedBack.instant())
                .getSeconds();

        // Các tick giả lập: tiến thêm 10 ns qua biên long có dấu.
        long startTick = Long.MAX_VALUE - 5;
        long nowTick = Long.MIN_VALUE + 4;
        long elapsedNanos = nowTick - startTick;

        System.out.println("eventAt=" + wall.instant());
        System.out.println("wallDeltaSeconds=" + wallDelta);
        System.out.println("elapsedNanos=" + elapsedNanos);
        System.out.println("expiredAt10=" + expired(startTick, nowTick, 10));
        System.out.println("expiredAt11=" + expired(startTick, nowTick, 11));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ClockKindsDemo.java
java ClockKindsDemo
```

Stdout:

```text
eventAt=2026-10-30T00:00:00Z
wallDeltaSeconds=-60
elapsedNanos=10
expiredAt10=true
expiredAt11=false
```

`wallDeltaSeconds=-60` đến từ việc chủ động tạo đồng hồ dịch lùi trong bài kiểm tra, không phải quan sát đồng hồ thực bị chỉnh. `elapsedNanos=10` đến từ phép trừ hai tick giả lập qua biên dấu. Chương trình không đo hiệu năng của JVM hay khẳng định giá trị thô thực tế của `nanoTime()` trên máy.

Hàm `expired` giả định hai tick theo đúng thứ tự thời gian, cùng nguồn và khoảng trôi qua trong miền đã nêu. Nó từ chối ngân sách âm; với dữ liệu sản xuất vẫn cần kiểm tra việc chuyển đổi `Duration` sang nano giây để phát hiện giá trị quá lớn thay vì để sai miền số.

## 8. Clock giúp kiểm thử ngày giờ, không tự kiểm soát nanoTime

`Clock` cho phép truyền nguồn ngày giờ vào đối tượng thay cho gọi trực tiếp `Instant.now()` khắp nơi. `Clock.fixed()` hữu ích cho kiểm thử thời điểm hết hạn; `Clock.offset()` hữu ích để mô phỏng một nguồn lệch thời gian. [API Clock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/time/Clock.html).

Nhưng `Clock.fixed()` không thay đổi `System.nanoTime()`. Nếu lớp nghiệp vụ vừa kiểm tra thời điểm lịch vừa quản lý ngân sách cục bộ, có thể truyền hai phụ thuộc tách biệt:

```java
Clock calendarClock = Clock.systemUTC();
LongSupplier elapsedTicker = System::nanoTime;
```

Đoạn minh họa cần import `java.time.Clock` và `java.util.function.LongSupplier`. Trong kiểm thử, cung cấp đồng hồ lịch giả và nguồn tick giả độc lập. Cách tách này cho phép kiểm tra rằng hiệu chỉnh ngày giờ không làm ngân sách trôi qua bị kéo dài hoặc âm một cách vô tình.

`Duration` chỉ là kiểu biểu diễn khoảng thời gian. `Duration.between(Instant.now(), laterInstant)` vẫn phụ thuộc hai thời điểm lịch đã chọn; `Duration.ofNanos(endTick - startTick)` phụ thuộc nguồn tick. Kiểu trả về giống nhau không bảo đảm phép đo có cùng tính chất.

## 9. Mốc lưu trữ, hệ phân tán và hết hạn cần cách thiết kế khác

Không lưu tick `nanoTime()` xuống cơ sở dữ liệu để JVM sau khởi động tiếp tục so sánh. Cũng không gửi tick thô của máy A sang máy B để tính độ trễ một chiều. Hai tiến trình có thể có mốc gốc khác nhau, nên hiệu hai giá trị đó không có nghĩa mong muốn.

Với dấu sự kiện và thời điểm hết hạn cần tồn tại qua khởi động lại, dùng biểu diễn thời điểm thích hợp như `Instant` cùng quy tắc kiểm tra nguồn giờ. Đồng bộ giờ giữa máy giúp vận hành nhưng vẫn có sai lệch; timestamp lịch một mình không bảo đảm thứ tự nhân quả của mọi sự kiện phân tán.

Với ngân sách trong cùng tiến trình, tick trôi qua giúp tránh phụ thuộc điều chỉnh đồng hồ lịch. Khi truyền ngân sách qua dịch vụ khác, cần giao thức deadline/ngân sách đã xác định và xử lý sai lệch nguồn giờ; không truyền trực tiếp tick cục bộ như một “deadline toàn cầu”.

Yêu cầu tính cả lúc máy ngủ, bị tạm dừng hoặc một thời gian rất dài cần được định nghĩa riêng theo nền tảng. Không giả định hợp đồng Java bảo đảm mọi hệ điều hành/JVM tính thời gian suspend giống nhau.

## 10. Đo hiệu năng: chọn đúng đồng hồ mới là bước đầu

Dùng `nanoTime()` đúng vẫn chưa đủ để kết luận một phương án mã nhanh hơn phương án khác. Đoạn mã nhỏ chịu ảnh hưởng của biên dịch JIT, giai đoạn làm nóng, loại bỏ mã không có tác dụng, cấp phát, GC và công việc nền. Một lần đo bằng tay chỉ là một quan sát trong điều kiện cụ thể.

Với microbenchmark cần so sánh đáng tin, dùng công cụ như JMH và thiết kế phép đo phù hợp. JMH là công cụ OpenJDK dành cho xây dựng/chạy/phân tích benchmark JVM; không biến ví dụ đọc đồng hồ thành bảng kết quả hiệu năng có ý nghĩa thống kê. [OpenJDK JMH](https://github.com/openjdk/jmh).

Nếu cần thời gian CPU thay cho thời gian trôi qua, đó là chỉ số khác. `ThreadMXBean` có khả năng đo CPU time của platform thread tùy hỗ trợ/cấu hình; không áp dụng mù quáng cho virtual thread và không coi số ấy tương đương độ trễ người dùng thấy. [API ThreadMXBean](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadMXBean.html).

Khi ghi nhận một yêu cầu thực tế, có thể giữ cả hai loại dữ liệu: timestamp lịch để tìm sự kiện trong log và duration đo bằng tick để báo độ trễ. Không cần cố quy đổi tick thô thành ngày giờ.

## 11. Những lỗi cần tự nhận diện

| Sai sót | Cách sửa về mô hình |
| --- | --- |
| Dùng `nanoTime()` làm timestamp ngày giờ | Dùng nguồn `Instant`/epoch cho dấu sự kiện |
| Dùng hiệu đồng hồ ngày giờ cho timeout cục bộ | Dùng nguồn đo khoảng trôi qua phù hợp |
| Cho rằng tick âm nghĩa là lỗi | Mốc gốc tùy ý; đánh giá hiệu hai tick |
| So sánh tick của hai JVM | Không có mốc chung theo hợp đồng API |
| Tính deadline bằng cộng rồi so sánh trực tiếp | Dùng phép trừ và miền khoảng hợp lệ |
| Cho rằng nanosecond nghĩa là mỗi lần đọc đều khác | Phân biệt đơn vị với độ phân giải |
| Đổi `Clock` rồi mong timeout dùng nanoTime đổi theo | Truyền nguồn tick giả riêng khi kiểm thử |
| Gọi elapsed time là CPU time | Xác định đúng chỉ số cần quan sát |

Tự kiểm tra: cần ghi một phiên kết thúc vào thời điểm lịch và đo nó kéo dài bao lâu. Lưu thời điểm kết thúc dưới dạng `Instant`; đo khoảng trong cùng JVM bằng hiệu tick. Nếu tiến trình khởi động lại giữa hai mốc, không dùng tick cũ để tiếp tục phép đo mà không có một thiết kế lưu trữ/thời gian riêng.
