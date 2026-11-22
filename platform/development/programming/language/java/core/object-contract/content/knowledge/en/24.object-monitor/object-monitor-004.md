# Object.wait(): nhả monitor khi chờ và phải giành lại trước khi tiếp tục

## 1. Ý nghĩa cốt lõi

Trong Java, mỗi đối tượng có một **intrinsic lock (monitor)** dùng bởi `synchronized`. Khi một luồng đang sở hữu monitor của đối tượng `lock` và gọi `lock.wait()`:

1. Luồng **tạm nhả toàn bộ quyền sở hữu monitor của chính `lock`** rồi đi vào trạng thái chờ. Luồng khác nhờ đó có thể vào `synchronized (lock)` để thay đổi điều kiện và phát thông báo.
2. Khi được thông báo, bị ngắt, hoặc tự thức dậy không có thông báo (spurious wakeup), luồng **chưa thể chạy tiếp ngay**. Nó phải **giành lại monitor của `lock`**; chỉ sau khi giành được monitor, `wait()` mới trả về bình thường hoặc ném `InterruptedException`.
3. Vì vậy, đoạn mã ngay sau `wait()` bên trong cùng khối `synchronized (lock)` luôn chạy khi luồng đã sở hữu lại monitor đó.

Điểm dễ nhầm nhất: **`notify()` / `notifyAll()` không lập tức chuyển monitor cho luồng đang chờ**. Luồng thông báo vẫn giữ monitor đến lúc thoát `synchronized` (hoặc nhả bằng cơ chế thích hợp).

## 2. Điều kiện tiên quyết: chờ trên đúng monitor đang sở hữu

Các phương thức `wait()`, `notify()` và `notifyAll()` thuộc `java.lang.Object`. Luồng gọi phải đang sở hữu **monitor của đúng đối tượng nhận lời gọi**:

```java
Object lock = new Object();

synchronized (lock) {
    lock.wait(); // Hợp lệ: đang sở hữu monitor của lock.
}
```

Đây là một *đoạn minh họa*, cần đặt trong phương thức xử lý hoặc khai báo `InterruptedException`; bản thân đoạn này sẽ chờ vô hạn nếu không có sự kiện đánh thức phù hợp.

Ngược lại:

```java
Object a = new Object();
Object b = new Object();

synchronized (a) {
    b.wait(); // IllegalMonitorStateException: không sở hữu monitor của b.
}
```

Quy tắc tương tự áp dụng cho `b.notify()` và `b.notifyAll()`. `synchronized(this)` cũng không trao quyền gọi `someOtherObject.wait()`, trừ khi `this` chính là đối tượng đó.

Monitor của `synchronized` trên phương thức thể hiện (instance synchronized method) là `this`; monitor của phương thức `static synchronized` là đối tượng `Class` tương ứng. Không được nhầm hai monitor đó.

## 3. Diễn tiến từ lúc chờ đến lúc tiếp tục

Giả sử hai luồng cùng dùng một `lock` và một biến điều kiện `ready`, đều chỉ đọc/ghi `ready` trong `synchronized (lock)`:

| Thời điểm | Luồng A (đang chờ) | Luồng B (đánh thức) | Monitor `lock` |
| --- | --- | --- | --- |
| 1 | Vào `synchronized (lock)`, thấy `ready == false` | Chưa vào | A sở hữu |
| 2 | Gọi `lock.wait()`: nhả monitor và chờ | Có thể tranh quyền vào | Được giải phóng |
| 3 | Tiếp tục chờ | Vào `synchronized (lock)`, đặt `ready = true` | B sở hữu |
| 4 | Được `notifyAll()` đánh thức nhưng chưa thể vượt qua `wait()` | Gọi `lock.notifyAll()` và vẫn ở trong khối khóa | B vẫn sở hữu |
| 5 | Cạnh tranh để giành lại monitor | Thoát `synchronized (lock)` | Được giải phóng |
| 6 | Giành lại monitor, `wait()` trả về, kiểm tra lại `ready` | Đã rời khối khóa | A sở hữu |

`notify()` chỉ chọn một luồng đang chờ trên đối tượng (không bảo đảm chọn luồng nào); `notifyAll()` đánh thức tất cả luồng đang chờ trên đối tượng. **Các luồng được đánh thức vẫn phải lần lượt cạnh tranh lấy monitor**, không được chạy song song trong cùng một monitor. Thứ tự giành monitor và thời điểm chạy không được bảo đảm.

Với `wait()` không thời hạn, Java thường biểu diễn luồng đang chờ là `WAITING`. Với `wait(timeout)`, luồng có thể ở `TIMED_WAITING`. Trong giai đoạn cố giành lại monitor, luồng có thể ở `BLOCKED`. Đây là mô hình để hiểu cơ chế, không nên viết chương trình dựa vào việc quan sát một ảnh chụp `Thread.State` chính xác từng thời điểm.

## 4. Chương trình Java 17+ kiểm chứng được

Lưu thành tệp `MonitorWaitDemo.java`:

```java
import java.util.concurrent.CountDownLatch;

public class MonitorWaitDemo {
    private static final Object MONITOR = new Object();
    private static boolean ready;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch waiterEntered = new CountDownLatch(1);

        Thread waiter = new Thread(() -> {
            synchronized (MONITOR) {
                System.out.println("waiter: before wait");
                waiterEntered.countDown();

                try {
                    while (!ready) {
                        MONITOR.wait();
                    }
                    System.out.println("waiter: resumed, owns monitor");
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    System.out.println("waiter: interrupted, owns monitor");
                }
            }
        }, "waiter");

        waiter.start();
        waiterEntered.await();

        synchronized (MONITOR) {
            System.out.println("main: acquired monitor");
            ready = true;
            MONITOR.notifyAll();
            System.out.println("main: notified, still owns monitor");
        }

        waiter.join();
    }
}
```

Biên dịch và chạy:

```bash
javac MonitorWaitDemo.java
java MonitorWaitDemo
```

Kết quả khi không có sự kiện ngắt từ bên ngoài:

```text
waiter: before wait
main: acquired monitor
main: notified, still owns monitor
waiter: resumed, owns monitor
```

**Vì sao thứ tự này có thể kiểm chứng?**

- `waiter` in dòng đầu khi đang giữ `MONITOR`. `CountDownLatch` chỉ bảo đảm luồng `main` không bắt đầu bước tranh monitor trước khi luồng chờ đi đến điểm đã báo hiệu; nó không thay thế cơ chế `wait/notifyAll`.
- Khi `main` in `main: acquired monitor`, nó đã giành được monitor mà `waiter` từng giữ. Trong mã này, `waiter` đã nhả monitor qua `wait()`; nếu không nhả, `main` không thể vào.
- Dù `main` đã gọi `notifyAll()`, dòng `waiter: resumed, owns monitor` chỉ được in **sau khi `main` rời khối `synchronized`** và `waiter` giành lại monitor.
- `ready` được đọc/ghi dưới cùng một monitor. Vòng `while` kiểm tra **điều kiện thực tế**, không giả định rằng một lần nhận thông báo luôn đồng nghĩa điều kiện đúng.
- `waiter.join()` giúp `main` chờ luồng con hoàn tất trước khi kết thúc. Không sử dụng `Thread.sleep()` để phỏng đoán thời điểm luồng khác chạy.

Nhánh `InterruptedException` trong ví dụ chỉ chạy nếu luồng chờ bị ngắt, nên không thuộc kết quả bình thường vừa liệt kê. Ngay trong `catch` ấy, `waiter` cũng đã giành lại `MONITOR`; sau đó ví dụ khôi phục cờ ngắt bằng `Thread.currentThread().interrupt()`.

## 5. Tại sao phải kiểm tra điều kiện bằng `while`?

`wait()` chờ **sự thay đổi điều kiện**, nhưng bản thân nó không mang theo điều kiện và không cam kết điều kiện đã đúng khi trả về. Nó có thể thức dậy vì một thông báo dành cho nhiều luồng, vì một thông báo không liên quan đến điều kiện của luồng cụ thể, hoặc do *spurious wakeup*. Giữa lúc được thông báo và lúc giành lại monitor, luồng khác cũng có thể thay đổi trạng thái.

Mẫu thông dụng:

```java
synchronized (lock) {
    while (!condition) {
        lock.wait();
    }

    // condition đã được kiểm tra khi đang giữ monitor lock.
    useSharedState();
}
```

Đây là **mã minh họa**, với `condition` và `useSharedState()` do chương trình cung cấp; phương thức chứa mã cần xử lý `InterruptedException`. Bên phát tín hiệu thay đổi điều kiện trong **cùng monitor**:

```java
synchronized (lock) {
    condition = true;
    lock.notifyAll();
}
```

Không dùng `if (!condition) lock.wait();` như thể một lần thức dậy là đủ. Cũng không gọi `wait()` trước rồi mới kiểm tra điều kiện: nếu tín hiệu đã đến trước đó, luồng có thể chờ vô hạn. Kiểm tra điều kiện và thao tác `wait()` cần nằm trong cùng vùng đồng bộ để không bỏ lỡ thay đổi ở khoảng trống giữa hai thao tác.

Một lời gọi `notifyAll()` **không lưu tín hiệu** để cấp cho luồng gọi `wait()` trong tương lai. Biến điều kiện là trạng thái có ý nghĩa; thông báo chỉ khiến các luồng xem xét lại trạng thái đó.

## 6. Những gì được nhả — và không được nhả

`lock.wait()` nhả **chỉ intrinsic monitor của đối tượng `lock`**. Nó không nhả một monitor khác mà luồng tình cờ đang giữ, và không tự động nhả `ReentrantLock` hoặc tài nguyên ngoài Java.

```java
synchronized (outer) {
    synchronized (lock) {
        lock.wait(); // Nhả lock, nhưng vẫn giữ monitor của outer.
    }
}
```

Đoạn này minh họa nguy cơ deadlock: nếu luồng muốn thay đổi điều kiện cần vào `synchronized (outer)`, nó có thể bị chặn bởi luồng đang chờ. Tránh giữ các khóa không liên quan xuyên qua một lần chờ.

Nếu luồng đã vào monitor của **cùng đối tượng** nhiều lần do khóa có tính tái nhập (reentrant), `wait()` nhả **toàn bộ số lần sở hữu monitor đó** khi chờ; trước khi tiếp tục, luồng phải giành lại monitor và khôi phục mức sở hữu tương ứng. Vì vậy `wait()` không chỉ giảm một mức đếm khóa.

## 7. Các cách `wait()` kết thúc và tác động của interruption

| Tình huống | Điều diễn ra |
| --- | --- |
| `notify()` hoặc `notifyAll()` | Luồng đang chờ được chọn/đánh thức, rồi **đợi giành lại monitor** mới trả về từ `wait()`. |
| `wait(timeout)` hết hạn | Luồng thức dậy khi hết thời gian chờ, nhưng vẫn phải **giành lại monitor** trước khi trả về. Không bảo đảm trả về đúng thời điểm hết hạn nếu monitor vẫn bị giữ. |
| Spurious wakeup | `wait()` có thể trả về mà không có tín hiệu hay timeout; vẫn phải giành lại monitor và kiểm tra điều kiện. |
| Luồng bị `interrupt()` | Luồng phải giành lại monitor trước khi `wait()` ném `InterruptedException`. Thông thường trạng thái ngắt được xóa khi ném ngoại lệ; mã bắt ngoại lệ quyết định xử lý hay đặt lại cờ ngắt. |

Các overload liên quan: `wait()` chờ không có thời hạn định trước; `wait(long timeoutMillis)` và `wait(long timeoutMillis, int nanos)` có thời hạn, với `timeoutMillis == 0` và `nanos == 0` nghĩa là chờ không thời hạn. Thời gian thức dậy thực tế phụ thuộc lịch chạy và cạnh tranh monitor. Sau bất kỳ cách thức dậy nào, **điều kiện phải được kiểm tra lại**.

Ví dụ kiểm tra bằng API chuẩn ngay sau khi `wait()` trở về:

```java
synchronized (lock) {
    while (!condition) {
        lock.wait();
        assert Thread.holdsLock(lock);
    }
}
```

`Thread.holdsLock(lock)` trả về `true` khi luồng hiện tại đang giữ intrinsic monitor của `lock`. Đoạn này là mã minh họa; có thể bật Java assertions bằng tùy chọn `-ea`. Trong đường ném `InterruptedException`, quyền sở hữu monitor cũng đã được phục hồi trước khi luồng đi vào `catch` nằm trong cùng khối `synchronized`.

## 8. So sánh với thao tác gần giống

| Thao tác | Có đòi sở hữu monitor của đối tượng nhận lời gọi? | Có nhả monitor khi chờ? | Điểm cần nhớ |
| --- | --- | --- | --- |
| `lock.wait()` | Có | **Có, của chính `lock`** | Phải giành lại trước khi trở về/ném ngoại lệ. |
| `lock.notify()` / `lock.notifyAll()` | Có | **Không** | Đánh thức luồng chờ; luồng phát thông báo vẫn sở hữu monitor cho đến khi nhả khóa. |
| `Thread.sleep(...)` | Không | **Không** | Chỉ tạm dừng luồng hiện tại; không thả những monitor mà luồng đang giữ. |
| `Condition.await()` cùng `ReentrantLock` | Phải giữ khóa liên kết với `Condition` | Nhả và tái giành **khóa liên kết**, không phải intrinsic monitor của `Object` | Cơ chế của `java.util.concurrent.locks`, không trộn trực tiếp với `Object.wait()`. |

## 9. Lỗi thường gặp và cách tránh

1. **Gọi trên sai đối tượng**: `synchronized (a)` nhưng gọi `b.wait()` hoặc `b.notifyAll()` gây `IllegalMonitorStateException`. Đồng bộ và gọi phương thức trên đúng cùng một đối tượng.
2. **Tưởng `notifyAll()` giao monitor ngay**: luồng chờ không chạy tiếp cho đến khi luồng phát tín hiệu nhả monitor và nó giành được lại.
3. **Chờ bên trong `if`**: lần thức dậy không bảo đảm điều kiện đúng. Dùng `while` và bảo vệ cả đọc/ghi trạng thái bằng cùng monitor.
4. **Gọi `wait()` dù điều kiện đã đúng**: tín hiệu không được lưu thành hàng đợi. Kiểm tra điều kiện trước khi quyết định chờ.
5. **Dùng `sleep()` để “nhường khóa”**: `Thread.sleep()` vẫn giữ monitor, dễ khiến luồng phát tín hiệu không vào được khối `synchronized`.
6. **Giữ monitor khác khi chờ**: `wait()` không nhả những monitor còn lại; có thể làm chuỗi luồng mắc kẹt.
7. **Nuốt `InterruptedException` mà không cân nhắc hủy tác vụ**: chọn cách xử lý phù hợp; khi không xử lý được tại chỗ, có thể khôi phục cờ ngắt hoặc truyền ngoại lệ lên tầng gọi.

## 10. Tự kiểm tra kiến thức

**Tình huống A.** Luồng A ở trong `synchronized (lock)` và gọi `lock.wait()`. Luồng B có thể vào `synchronized (lock)` không? **Có**, vì A đã nhả monitor đó khi chờ.

**Tình huống B.** B đã gọi `lock.notifyAll()` nhưng chưa ra khỏi `synchronized (lock)`. A có thể in dòng ngay sau `lock.wait()` không? **Không**, vì A còn phải giành lại monitor mà B vẫn đang giữ.

**Tình huống C.** A đang giữ cả `outer` và `lock`, sau đó gọi `lock.wait()`. Luồng khác có thể giành `outer` không? **Không**, vì `wait()` chỉ nhả monitor của `lock`.

**Tình huống D.** `wait()` trả về sau một thông báo có đồng nghĩa `condition == true` không? **Không**. Phải kiểm tra lại điều kiện trong `while` khi đã có monitor.

**Ghi nhớ:** `wait()` **nhả đúng monitor của đối tượng đang chờ để luồng khác có cơ hội thay đổi trạng thái**; khi chấm dứt việc chờ, luồng **bắt buộc giành lại monitor ấy trước khi tiếp tục**. Đây là lý do mẫu `synchronized` + điều kiện `while` + `wait/notifyAll` hoạt động an toàn khi tất cả truy cập trạng thái chung tuân theo cùng một khóa.
