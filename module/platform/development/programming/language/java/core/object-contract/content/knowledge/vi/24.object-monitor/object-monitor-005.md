# Thức dậy không bảo đảm điều kiện đã đúng

Trong cơ chế monitor của `Object`, một luồng gọi `wait()` vì **trạng thái dùng chung chưa thỏa mãn một điều kiện**. Khi `wait()` kết thúc bình thường, luồng chỉ biết mình đã có cơ hội kiểm tra lại trạng thái. Nó **không được phép suy ra điều kiện đã đúng** chỉ vì vừa được đánh thức.

Quy tắc cốt lõi: **luôn kiểm tra điều kiện trong vòng `while`, dưới cùng monitor bảo vệ dữ liệu đó**.

## 1. `wait()` và `notifyAll()` thực sự làm gì?

Giả sử hai luồng phối hợp qua một đối tượng `monitor` và cờ `ready`:

1. Luồng chờ giữ khóa monitor qua `synchronized (monitor)`, kiểm tra `ready`. Nếu `false`, nó gọi `monitor.wait()` và **nhả khóa monitor** trong lúc chờ.
2. Luồng khác lấy khóa đó, có thể cập nhật trạng thái, rồi gọi `monitor.notify()` hoặc `monitor.notifyAll()` khi đang giữ khóa.
3. Luồng được thông báo chỉ có thể tiếp tục từ `wait()` **sau khi lấy lại khóa monitor**. Trong khoảng từ lúc được thông báo tới lúc lấy lại khóa, trạng thái dùng chung có thể đã thay đổi.
4. Luồng chờ phải đọc lại `ready` khi đã giữ khóa; nếu vẫn `false`, nó chờ tiếp.

`notify()` chọn một luồng đang chờ trên monitor, còn `notifyAll()` thông báo cho tất cả luồng đang chờ trên monitor; **cả hai không gán giá trị cho `ready`, không xác nhận điều kiện và không trao khóa ngay lập tức**. Các luồng được đánh thức tiếp tục cạnh tranh để lấy monitor.

### Những nguyên nhân điều kiện vẫn sai sau khi thức dậy

- **Tín hiệu không đồng nghĩa điều kiện đúng:** luồng phát tín hiệu có thể gọi `notifyAll()` để báo rằng *có thay đổi*, nhưng thay đổi đó chưa đủ cho điều kiện của luồng chờ.
- **Luồng khác đến trước:** sau khi được thông báo, một luồng khác có thể lấy monitor, tiêu thụ phần tử cuối trong hàng đợi hoặc thay đổi trạng thái, rồi nhả khóa trước khi luồng đang thức dậy lấy được khóa.
- **Spurious wakeup (thức dậy tự phát):** Java cho phép `wait()` trở về bình thường dù không có thông báo tương ứng. Chương trình đúng phải xử lý trường hợp này.
- **Hết thời gian chờ:** với `wait(timeout)`, hàm có thể trở về do hết hạn; điều kiện vẫn cần kiểm tra.

Nếu bị ngắt khi chờ, `wait()` ném `InterruptedException` sau khi lấy lại monitor. Đây là nhánh xử lý ngắt riêng, không phải bằng chứng điều kiện đã thỏa mãn.

## 2. Sai với `if`, đúng với `while`

Ví dụ dưới đây là **đoạn mã minh họa** đặt bên trong một phương thức của lớp có `monitor` và `ready`:

```java
// SAI: chỉ kiểm tra điều kiện một lần.
synchronized (monitor) {
    if (!ready) {
        monitor.wait();
    }
    useResource(); // Có thể chạy khi ready vẫn false.
}
```

Ngay cả khi `ready` là `false` lúc bắt đầu chờ, `wait()` có thể trở về mà `ready` vẫn `false`. Lệnh sử dụng tài nguyên vì vậy có thể chạy sai.

```java
// ĐÚNG: điều kiện được kiểm tra lại mỗi lần quay về từ wait().
synchronized (monitor) {
    while (!ready) {
        monitor.wait();
    }
    useResource(); // Tại thời điểm giữ monitor này, ready == true.
}
```

Điểm quan trọng nằm ở **vòng lặp kiểm tra điều kiện**, không nằm ở số lần nhận `notify`. Mỗi lần quay về từ `wait()`, `while` đọc trạng thái mới dưới khóa; nếu điều kiện vẫn sai, luồng lại chờ. Luồng cập nhật `ready` cũng phải dùng **chính monitor này**, giữ tính nhất quán và quan hệ hiển thị bộ nhớ của `synchronized`.

## 3. Ví dụ Java 17+ có thể chạy

Chương trình sau chủ động gọi `notifyAll()` một lần **khi `ready` vẫn `false`**, rồi mới cập nhật `ready = true` và thông báo lần nữa. Hai `CountDownLatch` chỉ giúp điều phối thời điểm trong bản trình diễn; dữ liệu `ready` vẫn được bảo vệ bằng monitor của `Object`.

Lưu vào **`WaitPredicateDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;

public class WaitPredicateDemo {
    private static final Object monitor = new Object();
    private static boolean ready = false;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch firstWait = new CountDownLatch(1);
        CountDownLatch secondWait = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            synchronized (monitor) {
                int attempt = 0;
                while (!ready) {
                    attempt++;
                    System.out.println("worker: ready=false, wait #" + attempt);

                    if (attempt == 1) {
                        firstWait.countDown();
                    } else if (attempt == 2) {
                        secondWait.countDown();
                    }

                    try {
                        monitor.wait();
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        System.out.println("worker: bị ngắt, kết thúc");
                        return;
                    }
                }

                System.out.println("worker: ready=true, tiếp tục");
            }
        });

        worker.start();
        firstWait.await();

        synchronized (monitor) {
            System.out.println("main: notifyAll khi ready vẫn false");
            monitor.notifyAll();
        }

        secondWait.await();
        synchronized (monitor) {
            ready = true;
            System.out.println("main: ready=true rồi notifyAll");
            monitor.notifyAll();
        }

        worker.join();
    }
}
```

Biên dịch và chạy:

```bash
javac WaitPredicateDemo.java
java WaitPredicateDemo
```

Đầu ra minh họa trong một lần chạy thông thường (không có lần thức dậy tự phát phụ):

```text
worker: ready=false, wait #1
main: notifyAll khi ready vẫn false
worker: ready=false, wait #2
main: ready=true rồi notifyAll
worker: ready=true, tiếp tục
```

**Diễn giải:** sau `notifyAll()` đầu tiên, luồng `worker` lấy lại monitor, thấy `ready` vẫn `false` và vào `wait()` thêm lần nữa. Chỉ khi luồng `main` đổi `ready` thành `true` dưới monitor thì `worker` mới qua được điều kiện của `while`. Spurious wakeup có thể làm xuất hiện thêm một số lần chờ, nhưng không khiến `worker` đi qua vòng lặp khi `ready` còn sai.

## 4. Phân biệt nguyên nhân thức dậy với trạng thái cho phép chạy

Giả sử có nhiều waiter cùng chờ `ready == true`. Mỗi nguyên nhân thức dậy chỉ đưa luồng trở lại **điểm kiểm tra predicate**; không nguyên nhân nào thay thế được bước kiểm tra đó.

| Nguyên nhân `wait()` kết thúc bình thường | `ready` có chắc `true`? | Cách `while` xử lý |
| --- | --- | --- |
| `notifyAll()` khi `ready` vẫn `false` | Không | Giành lại monitor rồi chờ tiếp. |
| `notifyAll()` sau khi `ready` đã `true` | Không chắc ở thời điểm waiter lấy lại khóa; thread khác có thể đổi trạng thái | Đọc lại `ready`, chỉ đi tiếp nếu đúng. |
| Spurious wakeup | Không | Kiểm tra lại và chờ tiếp nếu điều kiện vẫn sai. |
| `wait(timeout)` hết hạn | Không | Kiểm tra trạng thái và ngân sách chờ theo hợp đồng timeout của caller. |

Một trường hợp đáng chú ý là **nhiều nhóm waiter chờ các điều kiện khác nhau trên cùng monitor**: producer chờ bộ đệm chưa đầy, consumer chờ bộ đệm không rỗng. `notifyAll()` đánh thức cả hai nhóm, nhưng mỗi luồng chỉ được làm việc khi predicate của nhóm mình đang đúng. Ví dụ Java hoàn chỉnh cho producer–consumer và giải thích chi tiết vòng `while` nằm ở bài **“Dùng vòng `while` kiểm tra điều kiện trước và sau khi chờ”**.

Nếu `wait()` ném `InterruptedException`, luồng đi vào **nhánh xử lý ngắt** sau khi giành lại monitor; đó không phải một lần trở về bình thường để coi điều kiện đã thỏa.

## 5. Checklist khi viết code với monitor

- **Gắn chờ với điều kiện cụ thể:** định nghĩa predicate, chẳng hạn `queue.isEmpty()` hoặc `!ready`, và kiểm tra lại predicate bằng `while`.
- **Một khóa cho việc kiểm tra, chờ và sửa trạng thái:** gọi `wait()`, `notify()` hay `notifyAll()` chỉ khi đang sở hữu monitor tương ứng; nếu không Java ném `IllegalMonitorStateException`.
- **Thay đổi trạng thái trước khi thông báo:** dưới cùng monitor, cập nhật dữ liệu chia sẻ rồi `notifyAll()` khi thay đổi có thể cho phép luồng khác tiến tiếp. Chỉ thông báo mà không cập nhật predicate có thể khiến tất cả lại chờ.
- **Không đặt công việc phụ thuộc điều kiện ngay sau `wait()` mà không kiểm tra lại.** Nếu `wait()` có timeout, vẫn phải xét predicate và chính sách hết hạn; timeout không đồng nghĩa thành công.
- **Xử lý ngắt có chủ đích:** nếu không thể tiếp tục khi `InterruptedException` xuất hiện, có thể khôi phục cờ ngắt với `Thread.currentThread().interrupt()` rồi kết thúc; không âm thầm nuốt ngắt.
- **Ưu tiên cấu trúc đồng bộ cấp cao khi phù hợp:** `BlockingQueue`, `CountDownLatch`, `Semaphore` hoặc `Condition` có thể giúp diễn đạt mục tiêu rõ hơn; nếu dùng `Condition.await()`, việc chờ điều kiện thông thường cũng cần vòng lặp kiểm tra predicate.

**Ghi nhớ:** tín hiệu đánh thức chỉ tạo *cơ hội kiểm tra lại*. **Điều kiện trên trạng thái dùng chung, được đọc trong `while` khi giữ đúng khóa, mới cho phép luồng tiếp tục.**
