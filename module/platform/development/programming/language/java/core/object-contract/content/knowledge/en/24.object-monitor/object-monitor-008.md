# Xử lý InterruptedException và thời hạn chờ theo hợp đồng của Object monitor

## 1. Bài toán và mục tiêu

Một thread muốn chờ trạng thái do thread khác thay đổi (ví dụ hàng đợi có dữ liệu, công việc đã hoàn thành) có thể dùng monitor của **Object** cùng với **wait**, **notify** và **notifyAll**. Hợp đồng chờ phải phân biệt ba kết cục: **điều kiện thỏa**, **hết thời hạn**, và **yêu cầu ngắt (interruption)**. Chúng không tương đương: thức dậy không chắc thành công; hết hạn không phải bị ngắt; bị ngắt không phải lỗi nghiệp vụ của điều kiện.

Bài này thuộc chủ đề **Monitor của Object** trong Java Core. Mục tiêu là viết đúng vòng lặp chờ predicate, thiết kế timeout có ngân sách tổng, xử lý **InterruptedException** mà không đánh mất tín hiệu hủy, và ghi rõ giới hạn của thời hạn chờ.

## 2. Hợp đồng của monitor và wait

Mỗi đối tượng Java có monitor. Thread phải **sở hữu monitor của chính đối tượng** khi gọi các phương thức **wait**, **notify** hoặc **notifyAll**; thường dùng **synchronized (monitor)**. Gọi không đúng monitor sẽ ném **IllegalMonitorStateException**.

| Phương thức | Hành vi quan trọng | Lưu ý |
| --- | --- | --- |
| **monitor.wait()** | Nhả monitor này và chờ; trước khi trả về hoặc ném **InterruptedException**, thread phải giành lại monitor. | Không nhả các monitor khác mà thread đang giữ; có thể thức dậy không cần notify (spurious wakeup). |
| **monitor.wait(long millis)** | Chờ tối đa theo mốc yêu cầu, có thể dậy do notify, timeout hoặc spurious wakeup; **millis = 0** nghĩa là chờ vô hạn. | millis âm gây **IllegalArgumentException**; không bảo đảm thời gian trả về chính xác. |
| **monitor.wait(long millis, int nanos)** | Bổ sung phần nanos trong khoảng **0..999999**; thời gian âm/nanos ngoài khoảng không hợp lệ. | Không hứa độ chính xác nanosecond. |
| **monitor.notify()** | Chọn một waiter trên cùng monitor để đánh thức. | Không chọn được waiter cụ thể; nó chỉ tiếp tục sau khi lấy lại monitor. |
| **monitor.notifyAll()** | Đánh thức các waiter trên cùng monitor. | Mỗi waiter phải tự kiểm tra lại điều kiện; không phải tất cả đều xử lý thành công. |

**wait trả về bình thường không chứng minh điều kiện đã đúng**, vì có thể timeout, có thông báo dành cho điều kiện khác, hoặc spurious wakeup. Luôn kiểm tra predicate trong **while** dưới cùng monitor:

~~~java
// Các trường monitor, ready thuộc cùng một đối tượng chia sẻ.
synchronized (monitor) {
    while (!ready) {
        monitor.wait();
    }
    // ready == true, kiểm tra lúc đang sở hữu monitor.
}

// Ở phía thread phát tín hiệu:
synchronized (monitor) {
    ready = true;
    monitor.notifyAll();
}
~~~

Đây là hai đoạn minh họa, không phải một chương trình Java độc lập. Predicate và thao tác đổi trạng thái cần cùng một khóa: đọc **ready** ngoài synchronized rồi mới gọi wait có thể bỏ lỡ thay đổi xảy ra giữa hai bước. Dùng **if** thay **while** dễ khiến thread tiếp tục dù điều kiện còn sai.

Khi **wait** đang chờ, nó nhả monitor của đối tượng gọi wait; khi kết thúc, phải giành lại monitor trước khi caller làm việc tiếp. Tương tự, **notifyAll** không trao monitor ngay cho waiter: thread báo tín hiệu vẫn giữ khóa đến khi thoát synchronized. Vì thế có thể có độ trễ sau khi đã được báo hoặc sau khi timeout.

## 3. InterruptedException: truyền tín hiệu ngắt theo hợp đồng

**Thread.interrupt()** là lời yêu cầu hợp tác để một thread dừng hoặc thay đổi công việc. Nếu thread đang trong **Object.wait**, thao tác wait sẽ ném **InterruptedException** theo hợp đồng xử lý ngắt; thread đã giành lại monitor khi ngoại lệ được ném. Interrupt flag được xóa khi ngoại lệ này được ném, nên caller chỉ kiểm tra lại flag có thể bỏ sót yêu cầu nếu ai đó đã nuốt ngoại lệ.

Chính sách xử lý phụ thuộc tầng gọi:

- **Phương thức ở tầng thấp có thể khai báo throws InterruptedException:** truyền ngoại lệ lên để caller quyết định hủy. Đây là cách rõ ràng nhất để không nhầm interruption với timeout.
- **Tầng không được khai báo ngoại lệ checked** (ví dụ **Runnable.run()**): khi catch, gọi **Thread.currentThread().interrupt()** để khôi phục flag và chấm dứt công việc chờ. Như vậy tầng bên ngoài vẫn có thể quan sát yêu cầu ngắt.
- **Không catch rỗng, không chỉ log rồi chờ lại** nếu chưa có chính sách rõ ràng. Điều này nuốt tín hiệu hủy và có thể làm tác vụ kẹt.
- **Không luôn vừa khôi phục flag vừa ném InterruptedException** theo thói quen: một tầng truyền ngoại lệ đã mang thông tin ngắt; việc khôi phục flag thường dành cho tầng bắt không thể truyền tiếp.

~~~java
// Trong một Runnable có trường gate kiểu Gate của ví dụ đầy đủ.
@Override
public void run() {
    try {
        boolean ready = gate.awaitOpen(java.time.Duration.ofSeconds(3));
        if (!ready) {
            return; // Hết hạn theo hợp đồng, không phải interruption.
        }
        // Chỉ xử lý tiếp khi điều kiện đã đúng.
    } catch (InterruptedException e) {
        Thread.currentThread().interrupt();
        return; // Giữ yêu cầu ngắt để caller/tầng ngoài có thể nhận biết.
    }
}
~~~

Đoạn trên là ví dụ từng phần; chương trình độc lập ở mục 5. **Thread.interrupted()** đọc rồi xóa cờ interrupt; nếu chỉ muốn quan sát mà không xóa, dùng **Thread.currentThread().isInterrupted()**. Sau khi đã khôi phục cờ, việc tiếp tục chạy một thao tác blocking mà không có chính sách hủy có thể làm nó lập tức ném InterruptedException lần nữa.

Cần nêu rõ độ ưu tiên khi **điều kiện đã đúng** và **interrupt flag đã được đặt**. Trong API mẫu bên dưới, nếu predicate đã đúng khi vào synchronized thì trả true mà không cần wait; interruption chỉ biểu hiện thành ngoại lệ khi lời gọi wait phải xử lý ngắt. Nếu muốn “đã bị interrupt thì hủy bất kể trạng thái”, phải thêm kiểm tra và ghi rõ hợp đồng riêng.

## 4. Timeout không phải một lần gọi wait cố định

Giả sử hợp đồng của API là “chờ điều kiện trong ngân sách 2 giây”. Mẫu sau **sai về tổng thời gian**:

~~~java
synchronized (monitor) {
    while (!ready) {
        monitor.wait(2_000); // Mỗi lần thức dậy lại cấp mới 2 giây.
    }
}
~~~

Nếu wakeup xảy ra nhiều lần trong khi predicate còn false, tổng thời gian có thể vượt xa 2 giây hoặc không kết thúc. Timeout không được cấp mới mỗi vòng. Phải đo **thời gian đã trôi qua** và tính lượng còn lại.

Sử dụng **System.nanoTime()** vì đây là nguồn thời gian phù hợp để đo khoảng cách giữa hai lần đọc; không dùng **System.currentTimeMillis()** để đo deadline khi đồng hồ tường có thể đổi do chỉnh giờ. Chỉ trừ các kết quả nanoTime để tính elapsed, không dùng giá trị nanoTime làm thời điểm trên lịch.

**TimeUnit.NANOSECONDS.timedWait(monitor, remainingNanos)** quy đổi ngân sách nanosecond dương thành wait phù hợp. Luôn kiểm tra **remainingNanos > 0** trước khi gọi; nếu tự gọi **wait(0)** vì làm tròn về 0 ms, tác vụ có thể chờ vô hạn.

Quy ước biên phù hợp cho API chờ predicate:
1. Timeout âm → **IllegalArgumentException**, không bắt đầu chờ.
2. Timeout bằng 0 → chỉ kiểm tra predicate một lần, trả true/false ngay.
3. Timeout dương → chờ bằng phần ngân sách còn lại, lặp lại khi chưa thỏa điều kiện.
4. Hết ngân sách và predicate còn false → trả **false**, không đánh đồng với **InterruptedException**.
5. Nếu predicate đã đúng lúc thread giành lại monitor (dù thời gian thực tế đã vượt ngân sách do tranh khóa), API mẫu trả **true**; true nói lên trạng thái quan sát, không chứng minh thay đổi đã đến trước deadline tuyệt đối.

Giới hạn: **synchronized** không cung cấp timeout khi thread đang tranh khóa *để vào* khối synchronized. Ngay cả khi wait hết hạn, thread có thể bị trì hoãn khi giành lại monitor hoặc được hệ điều hành lên lịch. Do đó timeout trong bài là ngân sách của vòng chờ điều kiện khi đã vào monitor, **không phải cam kết hàm trả về đúng trước một mốc cứng**.

## 5. Ví dụ Java 17+ biên dịch và chạy được

Tạo **MonitorContractDemo.java**:

~~~java
import java.time.Duration;
import java.util.Objects;
import java.util.concurrent.TimeUnit;

public class MonitorContractDemo {
    static final class Gate {
        private final Object monitor = new Object();
        private boolean open;

        void open() {
            synchronized (monitor) {
                open = true;
                monitor.notifyAll();
            }
        }

        /**
         * @return true nếu quan sát được open == true; false nếu
         *         hết ngân sách mà open vẫn false.
         * @throws InterruptedException nếu bị ngắt trong lúc wait.
         * @throws IllegalArgumentException nếu timeout âm.
         * @throws ArithmeticException nếu Duration.toNanos() tràn long.
         */
        boolean awaitOpen(Duration timeout) throws InterruptedException {
            Objects.requireNonNull(timeout, "timeout");
            if (timeout.isNegative()) {
                throw new IllegalArgumentException("timeout must be >= 0");
            }

            long budgetNanos = timeout.toNanos();

            synchronized (monitor) {
                long started = System.nanoTime();
                long remainingNanos = budgetNanos;

                while (!open) {
                    if (remainingNanos <= 0) {
                        return false;
                    }

                    // Chỉ truyền thời gian còn lại, không reset ngân sách.
                    TimeUnit.NANOSECONDS.timedWait(monitor, remainingNanos);

                    long elapsedNanos = System.nanoTime() - started;
                    remainingNanos = budgetNanos - elapsedNanos;
                }
                return true;
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Gate alreadyOpen = new Gate();
        alreadyOpen.open();
        System.out.println("Success: "
                + alreadyOpen.awaitOpen(Duration.ZERO));

        Gate neverOpen = new Gate();
        System.out.println("Timeout: "
                + neverOpen.awaitOpen(Duration.ofMillis(30)));

        Gate interruptedGate = new Gate();
        Thread worker = new Thread(() -> {
            try {
                interruptedGate.awaitOpen(Duration.ofSeconds(10));
                System.out.println("Interrupted: false");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
                System.out.println("Interrupted: true");
            }
        });

        worker.start();
        worker.interrupt();
        worker.join();
    }
}
~~~

Biên dịch bằng Java 17 trở lên:

~~~text
javac MonitorContractDemo.java
java MonitorContractDemo
~~~

Stdout mong đợi:

~~~text
Success: true
Timeout: false
Interrupted: true
~~~

Giải thích: Gate thứ nhất đã mở, nên chờ với **Duration.ZERO** vẫn trả true. Gate thứ hai không bao giờ được mở, nên trả false khi hết ngân sách. Gate thứ ba không mở và worker nhận yêu cầu interrupt; wait xử lý ngắt bằng ngoại lệ, worker khôi phục cờ trước khi thoát. Nếu interrupt đến trước lúc worker gọi wait, wait vẫn có thể phát hiện cờ khi được gọi: ví dụ không phụ thuộc vào việc worker đã kịp ngủ hay chưa.

Mọi truy cập biến **open** đều nằm trong **synchronized (monitor)**. Ghi trạng thái rồi nhả khóa và đọc trạng thái sau khi giành khóa tạo bảo đảm hiển thị bộ nhớ giữa các thread; biến **open** không cần volatile trong thiết kế này. **notifyAll()** đánh thức các waiter để họ kiểm tra lại predicate khi lấy được khóa. Không gọi **Thread.sleep** thay wait bên trong synchronized: sleep không nhả monitor, khiến thread phát tín hiệu có thể không lấy được khóa để đổi trạng thái.

**Về số học:** Duration lớn có thể khiến **toNanos()** ném **ArithmeticException**; đây là đầu vào không biểu diễn được trong ngân sách long nanosecond, không phải timeout thông thường. Trong ví dụ, thời lượng hợp lệ rất ngắn nên phép hiệu **System.nanoTime()** là phù hợp. Khi tự thiết kế hợp đồng có thời hạn rất lớn hoặc vô hạn, cần quyết định xử lý quá lớn một cách tường minh, không âm thầm chuyển thành **wait(0)**.

## 6. Thiết kế hợp đồng gọi và xử lý kết quả

| Tình huống khi giành monitor và kiểm tra | Kết quả của awaitOpen | Hành động phù hợp phía caller |
| --- | --- | --- |
| **open** đã true hoặc quan sát được true sau một lần thức dậy | **true** | Thực hiện bước yêu cầu Gate đã mở. |
| Hết ngân sách và **open** vẫn false | **false** | Báo hết hạn, thử lại có giới hạn, hoặc chọn phương án dự phòng. |
| Bị ngắt khi wait | Ném **InterruptedException** | Dừng tác vụ hoặc chuyển yêu cầu hủy lên tầng có trách nhiệm. |
| Timeout âm | Ném **IllegalArgumentException** | Sửa tham số đầu vào. |
| Duration không đổi được sang long nanoseconds | Ném **ArithmeticException** | Điều chỉnh hợp đồng về miền giá trị chấp nhận được. |
| Timeout null | Ném **NullPointerException** | Không truyền đối số null. |

Nếu một caller chọn retry sau **false**, phải dùng **ngân sách tổng** của toàn quy trình retry; không tái cấp timeout vô hạn mỗi vòng. Cũng cần thiết kế predicate đủ diễn đạt trạng thái terminal: một producer thất bại hoặc bị hủy có thể không bao giờ mở Gate. Trong hệ thống thật, nếu có **done**, **failed**, **cancelled**, phải định nghĩa nhánh xử lý các trạng thái đó; đừng chỉ chờ boolean không thể thành true.

Thông báo monitor không giữ lại như “phiếu” cho lần wait sau. Việc tránh bỏ lỡ tín hiệu đến từ **việc lưu trạng thái điều kiện dưới cùng monitor và kiểm tra trước khi chờ**, không phải từ số lần gọi notify. Với nhiều waiter chờ điều kiện khác nhau trên cùng monitor, **notifyAll** thường an toàn hơn **notify**, dù có thể đánh thức nhiều thread để rồi họ lại wait.

## 7. Những lỗi phổ biến và checklist

| Lỗi | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Gọi **wait/notify** không giữ đúng monitor | Vi phạm quyền sở hữu khóa; **IllegalMonitorStateException** | Dùng cùng đối tượng trong synchronized và khi gọi. |
| Dùng **if (!ready) wait()** | Thức dậy giả hoặc thông báo không làm ready đúng | Dùng vòng **while (!ready)**. |
| Kiểm tra predicate ngoài synchronized | Có thể đọc giá trị cũ, bỏ lỡ tín hiệu | Bảo vệ mọi lần đọc/ghi state bằng cùng monitor. |
| Catch InterruptedException rồi bỏ qua | Đánh mất tín hiệu hủy; chờ không kiểm soát | Truyền tiếp hoặc khôi phục flag và thoát ở tầng không truyền được. |
| Cứ lặp lại wait với cùng timeout | Ngân sách tổng bị reset | Tính lại thời gian còn lại sau mỗi lần thức dậy. |
| Dùng **wait(0)** cho “0 ms” | Thực tế là chờ vô hạn | Kiểm tra ngân sách hết trước khi wait. |
| Nghĩ notifyAll báo thành công | Wakeup không thay thế việc kiểm tra điều kiện | Predicate quyết định kết quả. |
| Dùng **currentTimeMillis** đo elapsed | Thay đổi đồng hồ tường làm sai deadline | Dùng hiệu **nanoTime**. |
| Quên tranh khóa và lịch thread | Hàm có thể trả về sau deadline | Mô tả phạm vi timeout chính xác trong API. |
| Dùng **sleep** khi giữ monitor | Sleep không nhả khóa, producer khó đổi state | Dùng wait có predicate. |

Trước khi hoàn tất code, tự hỏi: (1) Predicate có luôn được đọc và sửa dưới cùng monitor không? (2) Tất cả wait nằm trong **while** không? (3) Timeout 0 có trả ngay không? (4) Mỗi wakeup có trừ thời gian đã chờ không? (5) Interruption có đường xử lý riêng khỏi false không? (6) Tầng bắt ngoại lệ có truyền hoặc khôi phục cờ và dừng hợp lý không? (7) API có nói rõ rằng đây không phải deadline cứng của cả hàm không?

## 8. Câu hỏi tự ôn tập

1. Kể các lý do **wait(1000)** có thể trở về bình thường mà predicate vẫn false. Vì sao phải dùng while?
2. Khi **wait** ném **InterruptedException**, thread đã giành lại monitor chưa, và trạng thái interrupt flag ra sao?
3. Vì sao năm lần wakeup giữa vòng chờ có thể biến **wait(2000)** lặp lại thành tổng thời gian hơn 2 giây? Cách tính đúng?
4. Timeout bằng 0, timeout âm và thời hạn quá lớn khác nhau thế nào?
5. Tại sao không thể dùng synchronized + Object.wait để bảo đảm toàn bộ lời gọi luôn kết thúc trước deadline tuyệt đối?
6. Vì sao gọi notifyAll chỉ đúng khi state đã cập nhật dưới cùng monitor? Điều gì xảy ra nếu cập nhật ngoài khóa?

**Ghi nhớ:** **Object.wait** là cơ chế chờ và phối hợp monitor, không phải dấu hiệu hoàn thành nghiệp vụ. Hợp đồng đúng phân biệt rõ **thành công**, **hết hạn**, **ngắt**; dùng while kiểm tra state, ngân sách chờ còn lại và chính sách truyền/cất giữ tín hiệu interrupt.
