# `Object.wait()`, `notify()` và `notifyAll()` là phương thức `final` trong Java

Ba phương thức `wait()`, `notify()` và `notifyAll()` thuộc lớp `java.lang.Object`. Chúng giúp các luồng phối hợp thông qua **monitor nội tại (intrinsic monitor)** của một đối tượng. Điểm quan trọng của hợp đồng API: cả ba đều được khai báo `final`, nên lớp con **không thể override** để thay đổi cách các lời gọi này được phân giải. Tuy nhiên, `final` không có nghĩa là không thể gọi, không thể dùng với `synchronized`, hay bản thân chương trình sẽ tự động an toàn đa luồng.

## 1. Chữ ký và phạm vi của `final`

Các chữ ký công khai liên quan trong Java 17+ (minh họa khai báo API, không phải một lớp Java độc lập để biên dịch):

```java
public final void wait() throws InterruptedException;
public final native void wait(long timeoutMillis) throws InterruptedException;
public final void wait(long timeoutMillis, int nanos) throws InterruptedException;

public final native void notify();
public final native void notifyAll();
```

- `wait()` đưa luồng hiện tại vào tập chờ (*wait set*) của đối tượng nhận lời gọi, đồng thời nhả monitor của chính đối tượng đó. Trước khi tiếp tục thực thi sau `wait`, luồng phải giành lại monitor.
- `wait(long)` và `wait(long, int)` là các overload có thời gian chờ; `wait(0)` cũng có thể chờ vô thời hạn. Thời gian hết chỉ tạo cơ hội thức dậy, không bảo đảm điều kiện ứng dụng đã đúng.
- `notify()` chọn **một** luồng đang chờ trên monitor của đối tượng để đánh thức; không bảo đảm chọn luồng nào.
- `notifyAll()` đánh thức **tất cả** luồng đang chờ trên monitor đó. Các luồng vẫn phải lần lượt tranh chấp và giành lại monitor trước khi chạy tiếp.
- Cả ba phương thức là **instance method** được mọi lớp tham chiếu kế thừa từ `Object`. Phải gọi trên **đúng đối tượng dùng làm monitor**, ví dụ `monitor.wait()` và `monitor.notifyAll()`.

Trong chữ ký, `final` là thuộc tính cấm override; `native` (ở một số overload) là chi tiết triển khai. Hai từ khóa có ý nghĩa khác nhau.

## 2. Tại sao các phương thức này là `final`?

Một đối tượng Java có thể được dùng làm monitor bởi `synchronized (obj)`. `Object.wait` và `Object.notify/notifyAll` là giao diện chuẩn để tương tác với cơ chế chờ/đánh thức liên quan tới monitor đó. Không cho lớp con override các phương thức cùng chữ ký giúp hợp đồng gọi phương thức này ổn định ở mọi kiểu đối tượng, tránh việc một lớp con cung cấp hành vi có tên `wait`/`notify` nhưng phá vỡ kỳ vọng của mã đồng bộ.

Ví dụ dưới đây **cố ý không biên dịch được**, nhằm chứng minh giới hạn của `final`:

```java
class BadMonitor extends Object {
    @Override
    public void notify() { // Lỗi biên dịch: không thể override Object.notify() vì final
        System.out.println("fake notification");
    }
}
```

Tương tự, không thể override `notifyAll()` hoặc bất kỳ chữ ký `wait()` nào đã khai báo `final`. Viết thêm phương thức khác chữ ký, như `wait(String reason)`, về mặt ngôn ngữ là **overload**, không phải override; cách đặt tên này dễ gây nhầm lẫn và không mang ngữ nghĩa chờ monitor của `Object.wait()`.

Cần phân biệt rõ: **`final` bảo vệ khả năng override ở mức ngôn ngữ/API**; tính nguyên tử của thao tác chờ với việc nhả monitor và các quy tắc sở hữu monitor là ngữ nghĩa của cơ chế đồng bộ Java. `final` không thay thế việc khóa và kiểm tra điều kiện đúng cách.

## 3. Hợp đồng monitor khi gọi `wait` và `notify`

Giả sử nhiều luồng dùng chung đối tượng `monitor` và một biến trạng thái `ready`. Mẫu chuẩn:

```java
synchronized (monitor) {
    while (!ready) {
        monitor.wait();
    }
    // Ở đây đã giữ lại monitor và ready được kiểm tra là true.
}

// Ở một luồng khác:
synchronized (monitor) {
    ready = true;
    monitor.notifyAll();
}
```

Đây là **đoạn minh họa**, giả định `monitor` và `ready` là trạng thái chia sẻ được bảo vệ bằng cùng một monitor; ví dụ runnable đầy đủ có ở mục 4.

Trình tự quan trọng:

1. Luồng chờ vào `synchronized (monitor)` và giữ monitor. Không được gọi `monitor.wait()` nếu không đang giữ monitor của `monitor`.
2. Nếu điều kiện chưa thỏa, `wait()` **nhả monitor của `monitor`** và chờ. Nhờ vậy luồng khác mới có thể vào khối `synchronized` để thay đổi trạng thái.
3. Luồng phát tín hiệu vào cùng monitor, cập nhật trạng thái trước rồi gọi `notify()` hoặc `notifyAll()`. Lời gọi thông báo **không lập tức nhả monitor**; việc nhả diễn ra khi luồng phát tín hiệu rời khối đồng bộ (hoặc bằng cơ chế kết thúc giữ khóa tương ứng).
4. Luồng được đánh thức phải giành lại monitor. Sau đó vòng `while` **kiểm tra lại điều kiện**, vì điều kiện có thể đã đổi, nhiều luồng có thể cùng thức dậy hoặc có *spurious wakeup* (thức dậy không do thông báo theo cách lập trình viên dự kiến).

**Lý do dùng `while` thay vì `if`:** trạng thái được chia sẻ mới quyết định có thể tiếp tục hay chưa; sự kiện thức dậy không phải lời cam kết trạng thái sẽ luôn đúng. Thông báo cũng **không được lưu lại** để dành cho một lần `wait()` trong tương lai.

Ngoài ra, `wait()` nhả **chỉ monitor của đối tượng nhận lời gọi**; nếu luồng đang đồng thời giữ monitor khác, những monitor khác không được `wait()` tự động nhả.

## 4. Ví dụ Java 17+ chạy được: đợi tín hiệu mở cổng

File: `ObjectMonitorFinalDemo.java`

```java
import java.util.concurrent.CountDownLatch;

public class ObjectMonitorFinalDemo {
    private static final class Gate {
        private final Object monitor = new Object();
        private boolean open;

        void awaitOpen(CountDownLatch waiting) throws InterruptedException {
            synchronized (monitor) {
                while (!open) {
                    waiting.countDown();
                    monitor.wait();
                }
            }
        }

        void open() {
            synchronized (monitor) {
                open = true;
                monitor.notifyAll();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Gate gate = new Gate();
        CountDownLatch waiting = new CountDownLatch(1);
        Thread worker = new Thread(() -> {
            try {
                gate.awaitOpen(waiting);
                System.out.println("Worker: tiếp tục");
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        });

        worker.start();
        waiting.await();
        gate.open();
        worker.join();
        System.out.println("Main: hoàn tất");
    }
}
```

Biên dịch và chạy (terminal hỗ trợ UTF-8):

```bash
javac -encoding UTF-8 --release 17 ObjectMonitorFinalDemo.java
java ObjectMonitorFinalDemo
```

Stdout:

```text
Worker: tiếp tục
Main: hoàn tất
```

Giải thích:

- `monitor` là đối tượng khóa riêng, còn `open` là **điều kiện chia sẻ** được đọc/ghi trong cùng khối `synchronized (monitor)`.
- `awaitOpen` chờ khi `open == false`; lúc gọi `monitor.wait()`, luồng nhả monitor để `open()` có thể giành khóa, đặt `open = true` và `notifyAll()`.
- `CountDownLatch waiting` chỉ làm bước phối hợp trong **bài demo**: buộc luồng chính đợi tới lúc worker chuẩn bị chờ. Vì worker giữ `monitor` đến khi gọi `wait()`, luồng chính không thể mở cổng trước khi worker nhả monitor. Đây không phải điều kiện bắt buộc để dùng `wait/notifyAll`.
- `worker.join()` bảo đảm dòng `Worker: tiếp tục` xuất hiện trước `Main: hoàn tất`. Ví dụ đã được biên dịch và chạy bằng JDK 21 với mức tương thích `--release 17`.

Ở ví dụ, `Gate` cũng kế thừa các phương thức `final` của `Object`, nhưng cách sử dụng tốt hơn là khai báo một đối tượng `monitor` riêng, không public, để tránh mã bên ngoài can thiệp vào cùng khóa.

## 5. Chọn `notify()` hay `notifyAll()`

| Phương thức | Hiệu lực | Khi dùng |
| --- | --- | --- |
| `notify()` | Đánh thức một luồng bất kỳ trong wait set của đối tượng | Khi đã **chứng minh được** một luồng bất kỳ đang chờ đều có thể xử lý trạng thái mới và không làm kẹt tiến độ |
| `notifyAll()` | Đánh thức tất cả luồng đang chờ trên cùng đối tượng; từng luồng phải giành lại monitor | Lựa chọn dễ lập luận hơn khi có nhiều điều kiện hoặc nhiều loại luồng chờ; luôn kiểm tra điều kiện bằng `while` |

`notifyAll()` có thể khiến nhiều luồng thức dậy rồi lại chờ, nên có chi phí tranh chấp khóa; nó **không** cho các luồng chạy đồng thời bên trong cùng monitor. `notify()` có thể gây kẹt nếu đánh thức một luồng không thể làm việc tiếp, trong khi luồng cần thức dậy vẫn đang đợi. Khi chưa chứng minh rõ điều kiện chọn người chờ, ưu tiên tính đúng đắn với `notifyAll()`.

## 6. Lỗi phổ biến và cách tránh

**Gọi mà không sở hữu đúng monitor.** Đoạn sau sẽ ném `IllegalMonitorStateException` khi thực thi:

```java
Object lock = new Object();
lock.notifyAll(); // Chưa synchronized(lock)
```

Đúng là:

```java
Object lock = new Object();
synchronized (lock) {
    lock.notifyAll();
}
```

`wait()` cũng yêu cầu quyền sở hữu monitor tương ứng. `synchronized (this)` không cho phép gọi `other.wait()` nếu chưa giữ monitor của `other`.

**Dùng `if` để kiểm tra điều kiện trước khi chờ.** Có thể thức dậy không mong đợi hoặc điều kiện đã bị luồng khác thay đổi. Dùng vòng `while (!condition) lock.wait()`, với việc đọc/ghi `condition` dưới cùng khóa.

**Nhầm `Thread.sleep()` với `Object.wait()`.** `Thread.sleep(...)` tạm dừng luồng nhưng **không nhả** monitor mà luồng đang giữ; `Object.wait()` nhả monitor của đối tượng nhận lời gọi. `sleep` không phải cơ chế nhận `notify`.

**Cho rằng `notifyAll()` làm các luồng chạy ngay.** Luồng phát tín hiệu vẫn giữ monitor tới lúc ra khỏi khối đồng bộ; các luồng nhận tín hiệu sau đó mới có thể cạnh tranh để lấy lại khóa.

**Nhầm tín hiệu với trạng thái.** Nếu gọi `notifyAll()` lúc chưa có ai chờ, không có thông báo nào được ghi nhớ. Luôn lưu trạng thái có ý nghĩa (`open`, số phần tử trong hàng đợi, cờ hủy…) và kiểm tra trạng thái ấy trong vòng lặp.

**Bỏ qua ngắt luồng.** `wait()` có thể ném `InterruptedException`. Khi bị ngắt trong lúc chờ, luồng phải giành lại monitor trước khi phương thức hoàn tất việc ném ngoại lệ. Nếu bắt ngoại lệ mà không thể xử lý tại đó, thường nên lan truyền nó hoặc phục hồi cờ ngắt bằng `Thread.currentThread().interrupt()` như trong ví dụ.

**Cho rằng `final` đồng nghĩa thread-safe.** Một lớp có thể gọi `wait()`/`notifyAll()` đúng chữ ký nhưng vẫn sai vì truy cập trạng thái thiếu đồng bộ, dùng không cùng monitor, chờ sai điều kiện hoặc khóa chéo. Cần thiết kế giao thức phối hợp luồng đúng.

## 7. Cách ghi nhớ và áp dụng

- **`final`:** không override được `wait`, `notify`, `notifyAll` ở các chữ ký chuẩn của `Object`.
- **Cùng monitor:** `synchronized(lock)`, `lock.wait()` và `lock.notifyAll()` phải liên quan đúng đối tượng `lock`.
- **Điều kiện mới quan trọng:** cập nhật trạng thái dưới khóa, chờ bằng `while`; `notify/notifyAll` chỉ là tín hiệu yêu cầu kiểm tra lại.
- **Không kỳ vọng thứ tự:** `notify()` không chọn người chờ theo thứ tự được bảo đảm; `notifyAll()` không bảo đảm lịch chạy.

Trong ứng dụng có phối hợp phức tạp, API cấp cao như `BlockingQueue`, `CountDownLatch` hoặc `Lock`/`Condition` thường dễ kiểm soát hơn. Chúng không làm thay đổi sự thật cốt lõi: các phương thức monitor chuẩn được kế thừa từ `Object` vẫn là `final`.

### Tự kiểm tra

1. Vì sao `@Override public void notify()` trong lớp con báo lỗi? — Vì `Object.notify()` là `final`.
2. Luồng đang giữ `synchronized (a)` có được gọi `b.wait()` không? — Chỉ khi nó **cũng** đang sở hữu monitor của `b`; giữ monitor của `a` là chưa đủ.
3. `notifyAll()` xong là mọi luồng chờ chạy qua `wait()` ngay? — Không. Mỗi luồng còn phải lấy lại monitor rồi kiểm tra lại điều kiện trong vòng `while`.