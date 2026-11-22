# Dùng vòng `while` kiểm tra điều kiện trước và sau khi `wait()`

## 1. Vấn đề cần giải quyết

Khi nhiều thread cùng truy cập một đối tượng, một thread có thể phải **chờ trạng thái chung thỏa điều kiện** rồi mới tiếp tục. Ví dụ:

- Consumer chỉ được lấy dữ liệu khi bộ đệm **không rỗng**.
- Producer chỉ được thêm dữ liệu khi bộ đệm **chưa đầy**.
- Thread xử lý chỉ được chạy khi một cờ trạng thái đã chuyển thành `ready == true`.

Trong cơ chế **intrinsic monitor** của Java, thread có thể gọi `Object.wait()` để tạm ngừng và nhường monitor, còn thread khác dùng `notify()` hoặc `notifyAll()` để thông báo trạng thái có thể đã đổi. Tuy nhiên, **được đánh thức không đồng nghĩa với điều kiện đã đúng**.

Quy tắc quan trọng là:

> **Luôn kiểm tra điều kiện trong vòng `while` khi dùng `wait()`.** Vòng lặp kiểm tra trước lần chờ đầu tiên và kiểm tra lại sau mỗi lần `wait()` trả về.

```java
synchronized (lock) {
    while (!conditionIsTrue()) {
        lock.wait();
    }
    // Vẫn giữ monitor của lock; điều kiện vừa được kiểm tra lại.
    performOperationThatRequiresCondition();
}
```

Đây là đoạn minh họa khuôn mẫu: `lock`, `conditionIsTrue()` và `performOperationThatRequiresCondition()` cần được định nghĩa trong chương trình thực tế.

## 2. `while` bảo vệ điều kiện như thế nào?

Một lời gọi `wait()` trên đối tượng `lock` có các đặc điểm chính:

1. Thread **phải đang sở hữu monitor của chính `lock`**, thường bằng `synchronized (lock)` hoặc một phương thức `synchronized` của `lock`. Nếu không, Java ném `IllegalMonitorStateException`.
2. Khi thực sự chờ, `lock.wait()` đưa thread vào wait set của `lock` và **nhả monitor của `lock`**, cho thread khác cơ hội thay đổi trạng thái. Nó không tự động nhả các monitor khác mà thread đang giữ.
3. Một thread chờ có thể được đánh thức bởi `notify()`, `notifyAll()`, ngắt (`interrupt`), hết thời gian đối với `wait(timeout)`, hoặc **spurious wakeup** (thức dậy không có thông báo tương ứng).
4. Trước khi `wait()` hoàn tất, thread phải **giành lại monitor của `lock`**. Khi đó, thread khác có thể đã sửa trạng thái một lần nữa.
5. Vì vậy, sau khi trở lại từ `wait()`, `while` đọc lại điều kiện **dưới cùng monitor**. Nếu chưa đạt, thread tiếp tục chờ; nếu đã đạt, thread thực hiện thao tác ngay trong miền đồng bộ đó.

Cần phân biệt: `notifyAll()` làm các thread đang chờ đủ điều kiện tranh chấp monitor; **thread gọi `notifyAll()` vẫn giữ monitor cho tới khi rời khối/phương thức `synchronized`**. Một lời thông báo là tín hiệu *hãy kiểm tra lại*, không phải lời cam kết *bạn chắc chắn có quyền tiếp tục*.

### Vì sao `if` không an toàn?

```java
synchronized (lock) {
    if (queue.isEmpty()) {
        lock.wait();
    }
    return queue.removeFirst(); // Có thể lỗi nếu queue vẫn rỗng.
}
```

Giả sử consumer A và B cùng đang đợi dữ liệu. Producer thêm **một** phần tử rồi gọi `notifyAll()`. A giành monitor trước và lấy phần tử; B giành monitor sau. Với `if`, B đi thẳng đến `removeFirst()` mặc dù queue đã rỗng. Với `while`, B thấy điều kiện chưa đạt và quay lại `wait()`.

Ngay cả khi chỉ có một consumer, spurious wakeup cũng đủ làm cho `if` không đúng. Do đó, chuyển `if` thành `while` là yêu cầu **đúng đắn về logic**, không chỉ là biện pháp phòng lỗi hiếm gặp.

## 3. Ví dụ Java 17+: bộ đệm một phần tử

Bộ đệm chỉ giữ tối đa một số nguyên. Producer phải chờ khi ô đã có dữ liệu; consumer phải chờ khi ô còn rỗng. Cả hai dùng **monitor của chính đối tượng `Slot`** vì các phương thức đều là `synchronized`; lời gọi `wait()` và `notifyAll()` ở đây tương đương `this.wait()` và `this.notifyAll()`.

Lưu đoạn sau vào tệp **`WaitWhileDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

public class WaitWhileDemo {
    static final class Slot {
        private Integer value; // null nghĩa là ô đang trống.

        public synchronized void put(int next) throws InterruptedException {
            while (value != null) {
                wait(); // Nhả monitor của Slot khi phải chờ ô trống.
            }

            value = next; // Thay đổi trạng thái khi vẫn giữ monitor.
            notifyAll(); // Báo cho các thread đang chờ kiểm tra lại.
        }

        public synchronized int take() throws InterruptedException {
            while (value == null) {
                wait(); // Nhả monitor của Slot khi phải chờ dữ liệu.
            }

            int result = value;
            value = null; // Giải phóng ô cho lần put tiếp theo.
            notifyAll();
            return result;
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Slot slot = new Slot();
        List<Integer> received = new ArrayList<>();

        Thread producer = new Thread(() -> {
            try {
                for (int n = 1; n <= 3; n++) {
                    slot.put(n);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "producer");

        Thread consumer = new Thread(() -> {
            try {
                for (int n = 0; n < 3; n++) {
                    received.add(slot.take());
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "consumer");

        producer.start();
        consumer.start();
        producer.join();
        consumer.join();

        System.out.println(received);
    }
}
```

Biên dịch và chạy với Java 17 trở lên:

```bash
javac WaitWhileDemo.java
java WaitWhileDemo
```

Đầu ra khi không có thread nào bị ngắt ngoài ý muốn:

```text
[1, 2, 3]
```

Thứ tự lập lịch producer/consumer có thể thay đổi, nhưng các giá trị được truyền qua `Slot` theo thứ tự `1, 2, 3`. Chương trình chỉ in kết quả **sau cả hai `join()`**, nên đầu ra không phụ thuộc thứ tự các thông báo hay thời điểm chạy của từng thread. Danh sách `received` chỉ được consumer ghi và được main đọc sau `join()`.

**Phân tích điều kiện bảo vệ:**

| Phương thức | Điều kiện phải chờ | Điều kiện để tiếp tục | Trạng thái thay đổi |
| --- | --- | --- | --- |
| `put(next)` | `value != null` | `value == null` | `value = next` |
| `take()` | `value == null` | `value != null` | `value = null` |

Trong cả hai phương thức, việc **kiểm tra điều kiện → đọc/sửa trạng thái → gửi thông báo** diễn ra dưới cùng monitor. Nếu đọc điều kiện bên ngoài `synchronized` rồi mới gọi `wait()`, một thay đổi có thể lọt vào khoảng trống giữa hai thao tác, khiến thread bỏ lỡ tín hiệu và chờ vô hạn.

Đoạn demo phục hồi cờ interrupt trong các hàm `Runnable` vì `Runnable.run()` không khai báo `throws InterruptedException`. Trong ứng dụng thực tế cần thiết kế cơ chế dừng và lan truyền lỗi của các worker; ví dụ cố ý tập trung vào vòng chờ, không mô phỏng hủy tác vụ.

## 4. Vòng lặp hoạt động trước và sau lần chờ ra sao?

Xét consumer đang gọi `take()`:

1. Consumer chiếm monitor và kiểm tra `value == null`. Nếu đã có dữ liệu, **không gọi `wait()`**.
2. Nếu trống, consumer gọi `wait()`, nhả monitor và vào trạng thái chờ.
3. Producer vào `put()`, đặt `value` rồi gọi `notifyAll()` trong lúc giữ monitor.
4. Producer ra khỏi phương thức; consumer mới có cơ hội giành lại monitor để `wait()` trả về.
5. Consumer chạy **lại điều kiện `value == null` ở đầu `while`**. Nếu thread khác đã lấy dữ liệu, nó tiếp tục chờ. Nếu có dữ liệu, nó lấy giá trị, đặt `value = null`, thông báo và trả về.

Điểm mấu chốt: **không cần viết hai vòng `while` riêng biệt**. Một vòng `while` bao quanh `wait()` vừa kiểm tra *trước* lần chờ đầu, vừa kiểm tra *sau* mỗi lần thức dậy.

Các thread không được bảo đảm lần lượt giành monitor theo thứ tự đã chờ. `notifyAll()` không tạo ra fairness, không tự chuyển quyền sở hữu monitor cho consumer cụ thể và không thay thế kiểm tra predicate.

## 5. `notify()` và `notifyAll()` liên quan gì tới `while`?

- `notify()` chọn **một** thread trong wait set của monitor, nhưng không bảo đảm chọn thread đang đợi đúng loại điều kiện vừa trở thành true.
- `notifyAll()` đánh thức **tất cả** thread đang đợi monitor đó. Từng thread phải cạnh tranh lại để vào `synchronized`, rồi `while` quyết định thread nào thực sự có thể tiến hành.
- Khi nhiều kiểu thread cùng chờ trên một monitor, chẳng hạn producer chờ **not-full** và consumer chờ **not-empty**, dùng `notifyAll()` thường là lựa chọn đơn giản và an toàn hơn. `notify()` chọn nhầm nhóm thread có thể làm hệ thống tiếp tục chờ dù có thao tác khả thi.
- Dùng `notifyAll()` **không** cho phép thay `while` bằng `if`: nhiều thread có thể cùng thức dậy nhưng chỉ một thread có điều kiện phù hợp ở thời điểm lấy monitor.

Để tránh đánh thức nhiều thread không cần thiết ở hệ thống phức tạp, có thể dùng các `Condition` riêng với `ReentrantLock`; dù vậy, quy tắc **chờ trong vòng lặp kiểm tra predicate** vẫn giữ nguyên.

## 6. Ngắt, timeout và trường hợp điều kiện không bao giờ thỏa

### Ngắt (`InterruptedException`)

`wait()` có thể ném `InterruptedException` khi thread bị ngắt. Khi ném ngoại lệ này, trạng thái interrupt được xóa; thường nên **truyền tiếp ngoại lệ** bằng `throws InterruptedException`, hoặc khôi phục cờ bằng `Thread.currentThread().interrupt()` tại ranh giới không thể truyền tiếp. Không bắt rồi âm thầm bỏ qua, bởi caller sẽ mất tín hiệu yêu cầu dừng.

Một lần `wait()` bị ngắt không có nghĩa điều kiện đã đúng; đoạn code ngay sau vòng lặp **không nên chạy** nếu việc chờ kết thúc do ngoại lệ.

### Chờ có thời hạn

Dùng `wait(timeout)` thì thread còn có thể thức dậy do **hết hạn**; cần kiểm tra lại điều kiện y hệt. Không nên gọi lại cùng timeout nguyên vẹn sau mỗi lần thức dậy, vì nhiều lần thức dậy sớm có thể kéo dài tổng thời gian chờ vô hạn.

Ví dụ phương thức dưới đây là **đoạn minh họa đặt trong một lớp có `lock` và `ready` dùng chung**; đây không phải chương trình độc lập:

```java
boolean awaitReady(long timeoutNanos) throws InterruptedException {
    if (timeoutNanos < 0) {
        throw new IllegalArgumentException("timeoutNanos < 0");
    }

    long started = System.nanoTime();
    synchronized (lock) {
        long remaining = timeoutNanos;
        while (!ready) {
            if (remaining <= 0) {
                return false; // Hết hạn và điều kiện vẫn sai.
            }
            java.util.concurrent.TimeUnit.NANOSECONDS.timedWait(lock, remaining);
            remaining = timeoutNanos - (System.nanoTime() - started);
        }
        return true;
    }
}
```

Ở đây, mọi lần đọc/ghi `ready` phải được bảo vệ bằng chính `lock`. `System.nanoTime()` dùng để đo khoảng thời gian trôi qua; `TimeUnit.NANOSECONDS.timedWait` chuyển khoảng chờ thành lời gọi `Object.wait` phù hợp. Nếu cần deadline cực dài, chính sách timeout và xử lý tràn số cần được thiết kế riêng.

Lưu ý `wait(0)` có nghĩa **chờ vô thời hạn**, không phải kiểm tra rồi trả về ngay. Với `wait(long millis, int nanos)`, tham số phải nằm trong phạm vi API cho phép.

### Điều kiện không thể thỏa

Nếu không có thread nào cập nhật trạng thái hoặc phát tín hiệu thích hợp, `while` có thể chờ mãi. Hãy thiết kế thêm điều kiện kết thúc, cơ chế hủy hoặc deadline khi bài toán yêu cầu. Vòng `while` bảo đảm **không tiếp tục khi điều kiện sai**; tự nó không bảo đảm tiến triển.

## 7. Những lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Dùng `if` thay `while` | Thức dậy giả hoặc thread khác thay đổi trạng thái trước khi giành lại monitor | Kiểm tra predicate bằng `while` |
| Gọi `wait()` ngoài `synchronized` của cùng đối tượng | Không sở hữu monitor, gặp `IllegalMonitorStateException` | Khóa đúng đối tượng nhận `wait()` |
| Đọc điều kiện ở ngoài khóa | Trạng thái có thể đổi giữa lúc kiểm tra và chờ, gây mất tín hiệu | Bảo vệ cả predicate và thao tác với cùng monitor |
| Gọi `notifyAll()` trước khi cập nhật trạng thái hoặc quên phát tín hiệu | Thread được đánh thức nhưng không thấy trạng thái phù hợp; có thể chờ mãi | Cập nhật trạng thái rồi thông báo khi vẫn giữ monitor |
| Cho rằng `notifyAll()` giao ngay monitor | Thread báo hiệu vẫn đang giữ khóa; thread được báo phải đợi tranh chấp | Dự liệu thời điểm giành lại khóa |
| Bỏ qua `InterruptedException` | Yêu cầu hủy bị nuốt, thread khó dừng đúng cách | Truyền tiếp hoặc phục hồi cờ interrupt phù hợp |
| Giữ thêm khóa khác khi `wait()` | `wait()` chỉ nhả monitor của đối tượng nhận lời gọi; khóa khác vẫn bị giữ | Thiết kế thứ tự khóa và miền chờ để tránh deadlock |
| Thay `wait()` bằng `Thread.sleep()` khi đang giữ monitor | `sleep()` **không nhả monitor**, thread khác có thể không thay đổi được điều kiện | Dùng `wait()` đúng cách hoặc tiện ích đồng bộ cấp cao |

**Phân biệt thêm:** `wait()` của `Object` không giống `Thread.join()`, `Thread.sleep()` hay `LockSupport.park()`. Chúng có cơ chế và điều kiện sử dụng riêng. Bài này chỉ bàn về condition waiting với intrinsic monitor của `Object`.

## 8. Checklist tự kiểm tra

Với mỗi điểm chờ dựa trên `Object.wait()`, tự hỏi:

1. **Predicate là gì?** Ví dụ: “queue không rỗng”, không phải “đã nhận notify”.
2. **Ai bảo vệ predicate?** Mọi đường đọc/ghi liên quan đều phải tuân thủ cùng monitor.
3. **`while` có bao `wait()`?** Điều kiện được kiểm tra trước chờ và sau mỗi lần thức dậy.
4. **Ai thay đổi trạng thái và báo hiệu?** Sửa trạng thái trước, rồi `notifyAll()` khi giữ đúng monitor.
5. **Có đường ngắt, timeout và kết thúc không?** Thread không được âm thầm dùng dữ liệu chưa hợp lệ hoặc chờ vĩnh viễn ngoài ý muốn.

Khi sử dụng cấu trúc dữ liệu đồng thời thông dụng trong ứng dụng thực tế, ưu tiên API đã đóng gói giao thức chờ như `BlockingQueue.put()`/`take()`. Khi cần học, đánh giá hoặc tự xây dựng một monitor, vòng **`while (conditionNotSatisfied) wait()`** là nền tảng để giữ bất biến đúng dưới mọi cách lập lịch hợp lệ.
