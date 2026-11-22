# Tranh chấp dữ liệu và điều kiện tranh chấp

## 1. Hai thuật ngữ gần nhau nhưng không đồng nghĩa

Trong chương trình nhiều luồng, một kết quả sai có thể đến từ việc đọc/ghi dữ liệu không có quan hệ đồng bộ phù hợp, hoặc từ việc một chuỗi thao tác bị luồng khác chen vào giữa.

- **Tranh chấp dữ liệu (data race):** hai truy cập xung đột tới cùng biến dùng chung, ít nhất một truy cập ghi, mà không được sắp thứ tự bởi quan hệ happens-before theo mô hình bộ nhớ Java.
- **Điều kiện tranh chấp (race condition):** tính đúng của chương trình phụ thuộc vào thứ tự xen kẽ giữa các hoạt động, và một thứ tự hợp lệ có thể làm vi phạm quy tắc mong muốn.

Định nghĩa data race gắn trực tiếp với các truy cập bộ nhớ và happens-before. Race condition nói rộng hơn về tính đúng của một thuật toán hoặc quy trình. [JLS §17.4.5](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4.5)

Ví dụ, bán hai vé khi chỉ còn một vé là lỗi quy trình, dù từng lần đọc hay cập nhật bộ đếm đều dùng một lớp atomic.

## 2. Truy cập xung đột và happens-before

Hai luồng chỉ đọc cùng một biến không tạo xung đột đọc–ghi. Nếu một luồng ghi trong khi luồng khác đọc hoặc ghi cùng biến, cần xét cơ chế đồng bộ của chương trình.

Happens-before là quan hệ của mô hình bộ nhớ, không đơn giản là “tôi thấy lệnh này chạy trước trên đồng hồ”. Một số nguồn quan hệ thường dùng:

| Cơ chế | Ý nghĩa cần nhớ |
| --- | --- |
| Cùng một luồng | Có thứ tự hành động theo quy tắc chương trình |
| Cùng monitor | Mở khóa trước có quan hệ với lần khóa tiếp theo theo quy tắc Java |
| Ghi/đọc volatile | Có quy tắc công bố giá trị giữa các luồng |
| `Thread.start()` | Chuẩn bị trước khi start được công bố cho luồng được khởi động |
| `Thread.join()` hoàn tất | Bên join có thể quan sát các hành động đã hoàn tất của luồng kia |
| Công cụ concurrent | Có hợp đồng hiệu ứng bộ nhớ riêng, như latch và Future |

Các công cụ trong `java.util.concurrent` mở rộng những cơ chế này thành hợp đồng tiện dùng. [Hiệu ứng nhất quán bộ nhớ của concurrent](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/package-summary.html)

Không phải hai truy cập phải xảy ra cùng một nanosecond mới có vấn đề. Xen kẽ trên một bộ xử lý cũng có thể làm thuật toán sai.

## 3. Ví dụ data race trên bộ đếm thường

Đây là khai báo minh họa, không phải một chương trình có `main`:

```java
final class UnsafeCounter {
    private int count;

    void increment() {
        count++;
    }

    int value() {
        return count;
    }
}
```

Nếu hai luồng cùng gọi increment trên cùng một đối tượng mà không có đồng bộ bên ngoài phù hợp, các truy cập count không có thứ tự happens-before cần thiết. `count++` không phải một phép tăng nguyên tử; có thể hình dung nó gồm đọc giá trị, tính giá trị mới và ghi lại.

Một thứ tự gây mất cập nhật:

| Bước | Luồng A | Luồng B | Giá trị count |
| --- | --- | --- | --- |
| 1 | Đọc 0 | | 0 |
| 2 | | Đọc 0 | 0 |
| 3 | Ghi 1 | | 1 |
| 4 | | Ghi 1 | 1 |

Hai lời gọi tăng nhưng kết quả là 1 thay vì 2. Đây là mô hình giải thích một hành vi có thể xảy ra, không phải khẳng định mọi JVM đều thực thi bằng đúng bốn bước máy như bảng.

Một chương trình thử nhiều lần có thể in đúng tổng trong một số lần. Điều đó không chứng minh nó an toàn. Ngược lại, không nên ghi một stdout cố định cho phiên bản không đồng bộ vì kết quả phụ thuộc thực thi.

Mô hình bộ nhớ Java vẫn quy định các hành vi được phép; không diễn giải “có data race” thành “JVM được làm bất kỳ điều gì không giới hạn”.

## 4. Race condition vẫn có thể tồn tại khi từng thao tác là atomic

Giả sử chỉ còn một vé:

```java
if (remaining.get() > 0) {
    remaining.decrementAndGet();
    reserved.incrementAndGet();
}
```

Đây là đoạn minh họa với các biến AtomicInteger.

Mỗi lời gọi get hay decrementAndGet đều có hợp đồng atomic tương ứng. Nhưng **kiểm tra còn vé rồi trừ vé** là hai bước riêng. Cả hai luồng có thể đọc “còn một vé” trước khi bất kỳ luồng nào trừ. AtomicInteger không tự ghép khối if thành một giao dịch. [API AtomicInteger](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html)

Đây là lý do cần phân biệt an toàn của thao tác đơn với tính đúng của thao tác ghép.

## 5. Chương trình tái hiện điều kiện tranh chấp có kiểm soát

Để bài không dựa vào “hy vọng máy chạy trúng thời điểm”, chương trình dùng CountDownLatch buộc hai luồng cùng kiểm tra xong trước khi cập nhật. Phiên bản sửa dùng một phép compare-and-set để giành đúng một vé.

Lưu toàn bộ thành **ReservationRaceDemo.java**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

public class ReservationRaceDemo {
    public static void main(String[] args) throws Exception {
        demonstrateCheckThenAct();
        demonstrateCompareAndSet();
    }

    private static void demonstrateCheckThenAct()
            throws Exception {
        AtomicInteger remaining = new AtomicInteger(1);
        AtomicInteger reserved = new AtomicInteger();
        AtomicReference<Throwable> failure =
                new AtomicReference<>();
        CountDownLatch bothChecked = new CountDownLatch(2);

        Runnable reserve = () -> {
            try {
                boolean available = remaining.get() > 0;
                bothChecked.countDown();
                bothChecked.await();

                if (available) {
                    remaining.decrementAndGet();
                    reserved.incrementAndGet();
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                failure.compareAndSet(null, ex);
            }
        };

        runTwice(reserve);
        if (failure.get() != null) {
            throw new IllegalStateException(
                    "worker failed", failure.get());
        }

        System.out.println("unsafeRemaining=" + remaining.get());
        System.out.println("unsafeReserved=" + reserved.get());
    }

    private static void demonstrateCompareAndSet()
            throws InterruptedException {
        AtomicInteger remaining = new AtomicInteger(1);
        AtomicInteger reserved = new AtomicInteger();

        Runnable reserve = () -> {
            if (remaining.compareAndSet(1, 0)) {
                reserved.incrementAndGet();
            }
        };

        runTwice(reserve);
        System.out.println("casRemaining=" + remaining.get());
        System.out.println("casReserved=" + reserved.get());
    }

    private static void runTwice(Runnable action)
            throws InterruptedException {
        Thread first = new Thread(action, "first");
        Thread second = new Thread(action, "second");
        first.start();
        second.start();
        first.join();
        second.join();
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```shell
javac --release 17 -encoding UTF-8 ReservationRaceDemo.java
java ReservationRaceDemo
```

Kết quả chuẩn khi chương trình hoàn tất bình thường:

```text
unsafeRemaining=-1
unsafeReserved=2
casRemaining=0
casReserved=1
```

### Vì sao phiên bản sai có kết quả ổn định?

Cả hai luồng ghi vào biến cục bộ available trước khi cùng đi qua latch. Trước thời điểm đó không luồng nào được trừ remaining, nên cả hai đều thấy một vé còn lại. Sau khi latch mở, cả hai cùng thực hiện quyết định đã trở nên lỗi thời.

Latch là công cụ tổ chức thứ tự thực nghiệm, không phải cách sửa khối kiểm tra–cập nhật. Hợp đồng CountDownLatch bảo đảm hành động trước countDown có hiệu ứng happens-before với hành động sau lần await thành công tương ứng. [API CountDownLatch](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CountDownLatch.html)

Ví dụ này cố ý dùng AtomicInteger cho trạng thái chia sẻ để tập trung vào race condition của quy trình. Nó không dùng trường int thường không đồng bộ để minh họa data race như UnsafeCounter.

### Vì sao compareAndSet sửa được bài toán này?

Với đúng bài toán một vé và không nạp lại vé, `compareAndSet(1, 0)` thực hiện kiểm tra trạng thái kỳ vọng và cập nhật trong một thao tác atomic. Chỉ một luồng chuyển 1 thành 0 thành công. Luồng còn lại nhận false, nên không ghi nhận đặt vé.

Đây không phải thuật toán kho tổng quát có thể lấy nhiều vé, trả vé và thay đổi nhiều trường. Nếu bài toán mở rộng, phải thiết kế lại thao tác atomic hoặc phạm vi khóa; không kéo nguyên điều kiện 1 → 0 sang mọi tình huống.

reserved được tăng sau khi giành vé; chương trình chỉ kiểm tra hai bộ đếm sau khi join cả hai luồng. Nếu cần một ảnh chụp nhất quán giữa remaining và reserved **ngay giữa thực thi**, hai AtomicInteger độc lập chưa tự tạo một bản cập nhật chung.

## 6. Sửa thao tác ghép bằng một khóa chung

Một cách khác là bảo vệ toàn bộ điều kiện và cập nhật bằng cùng monitor:

```java
final class LockedInventory {
    private int remaining = 1;

    synchronized boolean reserve() {
        if (remaining <= 0) {
            return false;
        }
        remaining--;
        return true;
    }

    synchronized int remaining() {
        return remaining;
    }
}
```

Đây là một lớp đầy đủ có thể biên dịch, không có hàm main. Mọi luồng phải dùng cùng đối tượng LockedInventory và tuân thủ chính sách truy cập này.

Khóa bao trọn việc kiểm tra và trừ. Nếu tách thành hai phương thức synchronized `hasStock()` và `take()`, bên gọi vẫn có thể bị chen giữa hai lần gọi. Từng phương thức có khóa không tự làm chuỗi lời gọi bên ngoài nguyên tử.

Cũng không được để một đường truy cập khác đọc/ghi remaining trực tiếp bên ngoài chính sách khóa. Dùng hai khóa khác nhau cho cùng trạng thái không tạo cơ chế loại trừ mà thuật toán cần.

## 7. volatile giải quyết một phần, không giải quyết mọi phần

Một cờ dừng dùng chung có thể cần ngữ nghĩa volatile để một luồng công bố thay đổi cho luồng khác. Nhưng đổi `int count` thành `volatile int count` không tự biến `count++` thành phép tăng nguyên tử.

Cần phân biệt ba yêu cầu:

| Yêu cầu | Câu hỏi |
| --- | --- |
| Khả năng nhìn thấy | Luồng đọc có được bảo đảm quan sát việc công bố dữ liệu không? |
| Tính nguyên tử | Thao tác có bị luồng khác chen vào giữa các bước cần đi cùng nhau không? |
| Bất biến nghiệp vụ | Toàn bộ trạng thái có còn thỏa quy tắc, như số vé không âm không? |

Khả năng nhìn thấy không thay thế tính nguyên tử; tính nguyên tử của một biến không tự bảo vệ quan hệ giữa nhiều biến.

`Thread.sleep` và `yield` không phải cơ chế thiết lập đồng bộ bộ nhớ. Chèn sleep có thể đổi xác suất tái hiện lỗi, nhưng không tạo bằng chứng chương trình đúng. [JLS §17.3](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.3)

## 8. Cách tìm lỗi và chọn biện pháp

Khi kiểm tra một đoạn mã đồng thời, đi từ quy tắc cần giữ:

1. Xác định trạng thái dùng chung và mọi đường đọc/ghi.
2. Viết bất biến: số vé không âm, chỉ khởi tạo một lần, mỗi mã chỉ có một bản ghi.
3. Xác định thao tác nào phải được coi là một đơn vị.
4. Xem quan hệ happens-before giữa các truy cập bộ nhớ.
5. Chọn một giao thức nhất quán: khóa chung, thao tác atomic phù hợp, thông điệp qua queue hoặc sở hữu dữ liệu bởi một luồng.
6. Kiểm tra các thứ tự xen kẽ có thể phá điều kiện rồi viết thử nghiệm nhắm đúng thứ tự đó.

Với collection concurrent, quy tắc tương tự vẫn đúng: `containsKey` rồi `put` là hai lời gọi. Nếu cần thêm chỉ khi chưa có, phải xem thao tác ghép phù hợp của collection thay vì giả định tên “concurrent” làm mọi chuỗi lời gọi an toàn. [Tổng quan concurrent collections](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/package-summary.html)

Đối với dữ liệu trong cơ sở dữ liệu hoặc nhiều tiến trình, khóa Java của một instance không tự bảo vệ tất cả bên ghi. Cần cơ chế nhất quán ở phạm vi mà trạng thái thực sự được chia sẻ.

### Đọc kết quả kiểm thử đúng mức

Một stress test không phát hiện lỗi không chứng minh đã loại mọi data race hay race condition. Thay lịch chạy bằng latch/barrier có thể giúp tái hiện một tình huống cụ thể, nhưng còn cần lập luận về giao thức đồng bộ và bất biến.

Ngược lại, đừng “sửa” kiểm thử bằng cách thêm đồng bộ khiến nó không còn kiểm tra đúng tình huống cần quan sát. Chương trình trong bài nói rõ đang tái hiện check-then-act bằng thao tác atomic, không dùng nó để kết luận hành vi bộ nhớ của một trường thường.

### Những nhầm lẫn thường gặp

- Coi data race và race condition là hai tên luôn thay thế được.
- Nghĩ chỉ đa lõi mới tạo lỗi xen kẽ.
- Nghĩ đọc/ghi int đơn lẻ làm cả phép tăng trở nên nguyên tử.
- Đổi sang volatile rồi giữ nguyên thao tác ghép sai.
- Dùng lớp atomic nhưng vẫn kiểm tra và cập nhật bằng hai lời gọi độc lập.
- Đọc kết quả cuối sau join rồi tưởng join đã bảo vệ mọi cập nhật trước đó giữa hai luồng.
- Chọn khóa theo từng phương thức mà không xét đơn vị nghiệp vụ.

### Tự thực hành

1. Với UnsafeCounter, giải thích vì sao hai luồng join xong vẫn có thể đã mất cập nhật.
2. Bỏ latch khỏi phiên bản check-then-act: vì sao không còn được hứa stdout cố định?
3. Tách LockedInventory thành `hasStock` và `take` có khóa riêng từng lời gọi. Viết một thứ tự xen kẽ làm sai.
4. Mở bài toán thành ba vé và mỗi yêu cầu lấy một vé. Thiết kế phép cập nhật sao cho không âm; đừng dùng nguyên điều kiện chỉ kiểm tra 1.
5. Nếu một bên quan sát remaining và reserved trong lúc chạy, hãy nêu cơ chế cần thêm để thấy một trạng thái nhất quán của cả hai.
6. Nêu một trường hợp chỉ có một biến dùng chung nhưng nhiều bước nghiệp vụ, và một trường hợp cần bảo vệ quan hệ giữa hai biến.
