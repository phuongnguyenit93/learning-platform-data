# `notify()` không chuyển khóa ngay cho luồng được đánh thức

Khi một luồng gọi `notify()` trên một đối tượng trong Java, **luồng đang đợi có thể được chọn để thức dậy, nhưng không được trao ngay monitor lock**. Luồng gọi `notify()` vẫn giữ khóa cho đến khi nó thực sự nhả monitor. Chỉ sau khi giành lại đúng monitor, luồng được đánh thức mới có thể hoàn tất `wait()` và tiếp tục chạy phần mã được bảo vệ bởi `synchronized`.

Đây là điểm cần nắm vững khi phối hợp luồng bằng `Object.wait()`, `Object.notify()` và `Object.notifyAll()`.

## 1. Monitor, wait set và ý nghĩa của “đánh thức”

Mỗi đối tượng Java có một **monitor** (khóa dùng cho `synchronized`) và một **wait set** (tập các luồng đang chờ thông qua `wait()` trên chính đối tượng đó).

- `synchronized (lock) { ... }` yêu cầu luồng lấy monitor của `lock` trước khi vào khối. Trong lúc luồng giữ monitor, luồng khác không thể đồng thời đi vào vùng `synchronized` dùng cùng monitor.
- `lock.wait()` chỉ được gọi khi luồng đang giữ monitor của `lock`. Nó đưa luồng vào wait set và **nhả monitor của `lock`** trong khi chờ. Khi trở về từ `wait()`, luồng đã lấy lại monitor đó. Nếu luồng trước đó đã lấy monitor lồng nhau (reentrant), `wait()` giải phóng và sau đó lấy lại số lần sở hữu tương ứng theo đặc tả.
- `lock.notify()`, cũng phải gọi khi đang sở hữu monitor của `lock`, chọn tùy ý **một** luồng trong wait set của đối tượng này để cho phép tiếp tục chờ lấy khóa. Nếu không có luồng đang chờ thì lời gọi không có tác dụng lưu lại cho tương lai.
- `lock.notifyAll()` loại tất cả các luồng đang chờ khỏi wait set. Điều này **không** làm tất cả cùng chạy trong vùng `synchronized`: mỗi thời điểm chỉ một luồng có thể sở hữu monitor ấy.

Điểm phân biệt cốt lõi: **`wait()` nhả monitor khi bắt đầu chờ; `notify()` không nhả monitor khi báo hiệu**. Cách nói “luồng được đánh thức” chỉ có nghĩa luồng đó đủ điều kiện tiếp tục quá trình trở về từ `wait()`, chưa có nghĩa nó đã đi qua `wait()` hoặc đang thực thi.

## 2. Trình tự chính xác khi `notify()` được gọi

Giả sử hai luồng cùng dùng đối tượng `lock`: W (waiter) đợi điều kiện, N (notifier) thay đổi điều kiện và báo hiệu.

1. **W vào `synchronized (lock)`**, thấy điều kiện chưa thỏa và gọi `lock.wait()`. W nằm trong wait set, đồng thời nhả monitor để các luồng khác có thể vào.
2. **N lấy monitor**, cập nhật trạng thái chia sẻ rồi gọi `lock.notify()`. JVM chọn một luồng trong wait set (giả sử W). **N vẫn là chủ sở hữu monitor** ngay sau lời gọi.
3. **N tiếp tục chạy** các câu lệnh còn lại trong vùng `synchronized`. W chưa thể hoàn tất `wait()` bởi chưa thể lấy lại monitor đang do N giữ. Nếu N thực hiện xử lý chậm trong vùng khóa, W phải chờ thêm.
4. **N nhả monitor**, thường khi ra khỏi khối/phương thức `synchronized`. Từ thời điểm này, W có thể cạnh tranh lấy monitor với các luồng khác.
5. **Khi W lấy lại được monitor**, `wait()` mới có thể trả về bình thường (nếu không có tình huống ngắt), rồi W kiểm tra lại điều kiện và tiếp tục xử lý.

`notify()` không có cam kết về thời điểm chạy tiếp, thứ tự ưu tiên, tính công bằng hay việc W sẽ là luồng tiếp theo lấy khóa. Nếu có nhiều luồng đợi, `notify()` không bảo đảm chọn luồng nào. Trạng thái `Thread.State` quan sát được chỉ là ảnh chụp nhất thời; thường có thể thấy luồng bị chặn khi đợi monitor, nhưng không nên phụ thuộc vào một chuỗi trạng thái chính xác cho mọi JVM.

Có thể hình dung thứ tự bắt buộc với cùng monitor:

```text
W: giữ lock → wait() và nhả lock ──────────────┐
N:                   lấy lock → notify() → xử lý tiếp → nhả lock
W:                                                     tranh lock → wait() trở về
```

Thông báo làm W đủ điều kiện tiếp tục, **không phải thao tác “bàn giao khóa”** từ N sang W.

## 3. Chương trình Java 17+ chạy được, thứ tự kết quả ổn định

Lưu thành `NotifyMonitorDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class NotifyMonitorDemo {
    private static final Object MONITOR = new Object();
    private static final CountDownLatch WAITER_READY = new CountDownLatch(1);
    private static boolean canProceed = false;

    public static void main(String[] args) throws InterruptedException {
        Thread waiter = new Thread(() -> {
            synchronized (MONITOR) {
                WAITER_READY.countDown();
                try {
                    while (!canProceed) {
                        MONITOR.wait();
                    }
                    System.out.println("waiter: da lay lai monitor");
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            }
        }, "waiter");

        waiter.start();
        WAITER_READY.await();

        synchronized (MONITOR) {
            canProceed = true;
            MONITOR.notify();
            System.out.println("notifier: notify xong, van giu monitor");
            System.out.println("notifier: sap thoat synchronized");
        }

        waiter.join();
    }
}
```

Biên dịch và chạy:

```bash
javac NotifyMonitorDemo.java
java NotifyMonitorDemo
```

Kết quả chuẩn (ba dòng luôn theo thứ tự này nếu chương trình chạy bình thường, không bị ngắt từ bên ngoài):

```text
notifier: notify xong, van giu monitor
notifier: sap thoat synchronized
waiter: da lay lai monitor
```

**Giải thích vì sao kết quả ổn định:**

- `WAITER_READY.countDown()` xảy ra **bên trong** vùng khóa của waiter. Main chờ latch rồi mới cố lấy `MONITOR`; khi main vào được khối `synchronized`, waiter đã nhả monitor thông qua `wait()` (hoặc đã tạm thức dậy và chờ tiếp). Latch chỉ điều phối việc thiết lập ví dụ, không thay thế monitor trong cơ chế chính.
- `canProceed` được đọc và ghi khi đã giữ cùng `MONITOR`. Vòng `while` còn xử lý được trường hợp thức dậy không do thông báo (spurious wakeup); không cần `volatile` cho biến này trong ví dụ.
- Sau `MONITOR.notify()`, main vẫn ở trong khối `synchronized` nên in xong **cả hai dòng** của notifier trước khi waiter có cơ hội lấy lại monitor và in dòng của mình. Chương trình không dùng `sleep()` hoặc dự đoán lịch chạy để tạo ra thứ tự này.
- `waiter.join()` giúp main chờ luồng con kết thúc trước khi kết thúc chương trình; `join()` không phải thao tác bàn giao monitor ở chỗ gọi `notify()`.

Nếu thay dòng `MONITOR.notify()` bằng `MONITOR.notifyAll()`, với chỉ một waiter trong ví dụ, tính chất “không nhả khóa ngay” vẫn giữ nguyên.

## 4. Vì sao đặt việc chậm ngay sau `notify()` có thể gây trễ?

Xét **đoạn mã minh họa bên trong phương thức có `throws InterruptedException`**, sử dụng đối tượng monitor và biến điều kiện đã được khai báo:

```java
synchronized (monitor) {
    condition = true;
    monitor.notify();
    Thread.sleep(500); // Luồng báo hiệu vẫn giữ monitor trong lúc ngủ.
}
```

`Thread.sleep(500)` tạm dừng luồng gọi nhưng **không giải phóng monitor**. Dù một waiter đã được `notify()` chọn, nó vẫn không thể trở về từ `wait()` cho đến khi luồng báo hiệu rời khối `synchronized` (và waiter lấy lại khóa). Thời lượng ngủ thực tế không phải cam kết thời gian chờ chính xác.

Tương tự, thực hiện I/O, tính toán tốn thời gian hoặc đợi tài nguyên khác trong vùng khóa sau `notify()` có thể kéo dài thời gian chờ. Nên giữ đoạn bảo vệ ngắn, cập nhật trạng thái và báo hiệu dưới monitor, rồi làm các công việc không cần khóa ở bên ngoài.

Nếu notifier tự gọi `wait()` trên cùng monitor thì thao tác `wait()` của notifier **có** giải phóng monitor; đó là hành vi riêng của `wait()`, không phải do `notify()` đã chuyển khóa. Ra khỏi `synchronized` bình thường hoặc do ngoại lệ cũng nhả monitor theo quy tắc của khối.

## 5. Mối liên hệ với tính nhìn thấy của dữ liệu

Việc waiter phải lấy lại monitor còn bảo đảm một phần quan trọng của tính đúng đắn:

- N ghi `canProceed = true` khi giữ monitor, rồi nhả monitor lúc rời `synchronized`.
- Lần mở khóa của N **happens-before** lần lấy khóa tiếp theo của W trên cùng monitor. Vì thế, sau khi W lấy lại khóa, nó nhìn thấy các cập nhật phù hợp với quy tắc Java Memory Model.
- Đặc tả cũng có quy tắc đồng bộ giữa tác vụ thông báo và lần trở về từ `wait()` được thông báo; tuy nhiên **không quy tắc nào biến `notify()` thành thao tác nhả khóa ngay lập tức**.

Không được dựa vào việc gọi `notify()` mà tự bỏ `synchronized` quanh việc kiểm tra và cập nhật trạng thái dùng chung. Hai bên phải thống nhất đối tượng khóa và điều kiện.

## 6. Mẫu phối hợp đúng theo điều kiện

Hai đoạn sau là **mã mẫu trong các phương thức phù hợp**, với `monitor` là cùng một đối tượng và `condition` là trạng thái chia sẻ luôn được bảo vệ bởi monitor:

**Luồng chờ:**

```java
synchronized (monitor) {
    while (!condition) {
        monitor.wait();
    }
    // Điều kiện đã thỏa, và luồng đang giữ monitor.
}
```

**Luồng báo hiệu:**

```java
synchronized (monitor) {
    condition = true;    // Đổi trạng thái trước khi thông báo.
    monitor.notifyAll(); // Luồng chờ vẫn phải giành lại monitor.
}
```

Hãy nhớ rằng `wait()` có thể trở về do thông báo, do ngắt, do hết hạn với bản `wait(timeout)`, hoặc do **spurious wakeup**. Vì vậy, điều kiện phải được kiểm tra trong **`while`**, không chỉ trong `if`. `wait()` dạng không timeout vẫn có thể bị `InterruptedException`; mã bao quanh phải xử lý hoặc khai báo ngoại lệ đó. Nếu waiter thức dậy nhưng điều kiện lại không còn đúng vì một luồng khác đã xử lý trước, vòng `while` đưa waiter vào chờ tiếp.

Tín hiệu `notify()` **không được lưu lại**: nếu gọi khi wait set rỗng, một luồng bắt đầu `wait()` sau đó sẽ không nhận lại tín hiệu cũ. Việc đặt phép kiểm tra điều kiện và lời gọi `wait()` trong cùng vùng `synchronized` tránh khe hở kiểm tra–chờ có thể gây mất tín hiệu ở mô hình dùng đúng monitor.

Chọn `notify()` khi có thể chứng minh việc đánh thức tùy ý một waiter là đủ và đúng; chọn `notifyAll()` khi có nhiều waiter hoặc nhiều điều kiện chờ, vì `notify()` có thể đánh thức một luồng không đáp ứng được điều kiện cần tiến triển. `notifyAll()` có chi phí đánh thức thêm luồng nhưng vẫn không cho chạy đồng thời trong cùng monitor.

## 7. Lỗi thường gặp và cách sửa

| Hiểu sai / cách viết | Điều thực sự xảy ra | Cách xử lý |
| --- | --- | --- |
| “Gọi `notify()` là waiter chạy ngay.” | Notifier tiếp tục giữ monitor; waiter phải chờ và lấy lại khóa. | Chỉ dựa trên điều kiện chia sẻ, không giả định thứ tự chạy tức thì. |
| Gọi `monitor.notify()` ở ngoài `synchronized (monitor)`. | Ném `IllegalMonitorStateException` do không giữ đúng monitor. | Lấy khóa **cùng đối tượng** khi gọi `wait/notify/notifyAll`. |
| Dùng `if (!condition) monitor.wait();`. | Spurious wakeup hoặc cạnh tranh điều kiện khiến luồng tiếp tục sai. | Kiểm tra lại điều kiện bằng `while`. |
| Đổi điều kiện ngoài khóa, sau đó mới thông báo. | Có thể gây race hoặc lỗi nhìn thấy dữ liệu và phá vỡ giao thức chờ. | Bảo vệ cả cập nhật, kiểm tra và thao tác báo hiệu bằng cùng monitor. |
| Gọi `notify()` trên đối tượng khác đối tượng mà waiter dùng `wait()`. | Wait set thuộc từng đối tượng; waiter không được đánh thức bằng thông báo đó. | Dùng cùng đối tượng monitor thực sự. |
| Giữ monitor để làm I/O hoặc `sleep()` sau `notify()`. | Waiter có thể bị chặn lâu dù đã được thông báo. | Thu ngắn vùng khóa; dời việc không cần khóa ra ngoài. |
| Cho rằng `notifyAll()` trao khóa cùng lúc cho mọi waiter. | Mọi waiter được phép tiếp tục, nhưng từng luồng phải giành khóa một cách loại trừ. | Viết điều kiện đúng, chấp nhận cạnh tranh và kiểm tra lại. |
| Bỏ qua `InterruptedException` hoặc giả định chỉ `notify()` mới làm `wait()` trở về. | Luồng chờ có thể bị ngắt; chương trình dễ treo hoặc bỏ sót yêu cầu dừng. | Có chiến lược xử lý ngắt rõ ràng và vòng kiểm tra điều kiện. |

## 8. Câu hỏi kiểm tra

**Hỏi:** Sau `notify()`, notifier còn thực hiện 100 câu lệnh trong cùng khối `synchronized`. Waiter có thể tiếp tục ngay sau `wait()` trong lúc đó không?

**Đáp:** Không, nếu cả hai thao tác dùng cùng monitor. Waiter phải lấy lại monitor trước khi `wait()` kết thúc, nên phải chờ notifier nhả khóa. Số lượng câu lệnh không quan trọng; ranh giới sở hữu monitor mới quyết định.

**Hỏi:** Ngay khi notifier ra khỏi `synchronized`, waiter có chắc chắn chạy trước một luồng thứ ba đang cố lấy khóa không?

**Đáp:** Không. Java không bảo đảm waiter được `notify()` chọn sẽ giành monitor kế tiếp; các luồng có thể cạnh tranh.

**Hỏi:** Nếu không có waiter nào vào `wait()` lúc `notify()` được gọi thì sao?

**Đáp:** Không có thông báo tồn đọng. Một waiter xuất hiện sau đó chỉ có thể tiến triển nếu điều kiện cho phép, được báo hiệu trong tương lai hoặc có nguyên nhân thức dậy khác.

## 9. Ghi nhớ và tài liệu gốc

**Công thức nhớ:** `wait()` = chờ và nhả monitor; `notify()` = báo cho một waiter nhưng **vẫn giữ monitor**; waiter trở về từ `wait()` = **đã lấy lại monitor**.

- [Java Language Specification §17.1: Synchronization](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.1)
- [Java Language Specification §17.2.1–17.2.2: Wait và Notification](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.2)
- [Java Language Specification §17.4.5: Happens-before](https://docs.oracle.com/javase/specs/jls/se17/html/jls-17.html#jls-17.4.5)
- [Java SE 17 API: `Object`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html)
