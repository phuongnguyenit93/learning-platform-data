# await, signal và signalAll

## 1. Khóa bảo vệ trạng thái; Condition giúp chờ trạng thái thay đổi

Một khóa giúp một luồng đọc/ghi dữ liệu dùng chung trong vùng được bảo vệ. Nhưng nếu dữ liệu chưa cho phép tiếp tục, chẳng hạn hộp thư đang rỗng, luồng không nên vừa giữ khóa vừa tự quay chờ. Nó cần nhường khóa để bên khác tạo ra dữ liệu rồi mới kiểm tra lại.

`Condition` cung cấp cơ chế chờ ấy. `await()` cho phép luồng tạm chờ và nhả khóa gắn với condition; `signal()` đánh thức một luồng chờ; `signalAll()` đánh thức tất cả luồng chờ trên chính condition đó.

Điều kiện thực sự vẫn là một biểu thức trên dữ liệu, chẳng hạn `slot != null` hoặc `closed`. Đối tượng `Condition` không tự biết biểu thức nào đúng, không lưu dữ liệu công việc và không tự thay đổi trạng thái thay ứng dụng.

Bài dùng condition tạo từ `ReentrantLock`, một cơ chế vẫn áp dụng trong Java hiện đại. Ví dụ chạy được với Java 17 trở lên.

## 2. Tạo condition từ đúng khóa bảo vệ

```java
// Đoạn khai báo trong một lớp.
private final ReentrantLock lock = new ReentrantLock();
private final Condition notEmpty = lock.newCondition();
private final Condition notFull = lock.newCondition();
```

Cả hai condition cùng gắn với `lock` nhưng là hai tập luồng chờ khác nhau. Consumer đợi có dữ liệu trên `notEmpty`; producer đợi có chỗ trên `notFull`. Việc tách nhóm giúp thông báo đúng loại thay đổi.

Với condition của `ReentrantLock`, luồng phải giữ chính khóa ấy khi gọi `await`, `signal` hoặc `signalAll`. Nếu không giữ, lời gọi ném `IllegalMonitorStateException`. Giữ một khóa khác, hoặc chỉ giữ monitor bằng `synchronized(condition)`, không đáp ứng yêu cầu này.

Không trộn `condition.wait()`/`notify()` với `condition.await()`/`signal()`. Đó là các cơ chế khác nhau dù cùng được gọi trên một đối tượng Java. Hợp đồng tạo condition nằm trong [ReentrantLock.newCondition — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html#newCondition()).

## 3. await thực hiện việc gì?

Mẫu cốt lõi là kiểm tra điều kiện trong khóa, chờ nếu chưa đúng, rồi kiểm tra lại:

```java
// Đoạn minh họa trong phương thức throws InterruptedException.
lock.lockInterruptibly();
try {
    while (!ready) {
        changed.await();
    }
    // ready đang đúng và luồng đang giữ lock.
} finally {
    lock.unlock();
}
```

`ready` và `changed` trong đoạn này là trạng thái và condition của cùng một giao thức khóa. Diễn biến bình thường của một lần chờ:

1. Luồng đang giữ khóa và thấy điều kiện chưa cho phép tiếp tục.
2. `await()` thực hiện việc nhả khóa gắn với condition và đưa luồng vào chờ theo cơ chế nguyên tử của thao tác chờ.
3. Trong lúc chờ, luồng khác có thể lấy khóa và thay trạng thái.
4. Sau tín hiệu, ngắt hoặc một lần thức dậy giả, luồng chờ phải lấy lại khóa trước khi tiếp tục theo hợp đồng.
5. Khi `await()` trả về bình thường, luồng đang giữ khóa và quay lại kiểm tra điều kiện trong `while`.

Nếu trước khi chờ luồng đã tái nhập `ReentrantLock` nhiều lần, việc chờ giải phóng quyền giữ để bên khác có thể chạy, rồi khôi phục số mức giữ khi lấy lại khóa. `await` không chỉ tương đương với một lần `unlock()` thủ công.

`await()` không nhả mọi khóa khác mà luồng có thể đang giữ. Nếu giữ khóa A rồi chờ condition của khóa B, A vẫn có thể cản luồng cần làm điều kiện đúng. Cần xét toàn bộ vòng phụ thuộc tài nguyên.

## 4. Vì sao luôn kiểm tra bằng while?

Một luồng được đánh thức không có nghĩa điều kiện chắc chắn đúng lúc nó tiếp tục:

- Nền tảng cho phép thức dậy giả (spurious wakeup), không cần một tín hiệu tương ứng.
- Một luồng khác có thể lấy khóa trước và tiêu thụ dữ liệu/chỗ trống vừa xuất hiện.
- Tín hiệu có thể liên quan tới thay đổi vòng đời như đóng hộp thư, nên luồng phải chọn nhánh tiếp tục hoặc kết thúc.

Đổi `while` thành `if` có thể khiến luồng đi tiếp khi dữ liệu không còn đủ điều kiện. Việc kiểm tra lại phải xảy ra dưới cùng khóa bảo vệ dữ liệu, không kiểm tra một lần ngoài khóa rồi chờ bên trong.

Điều kiện để đúng giao thức là **trạng thái được bảo vệ + vòng kiểm tra + thông báo sau thay đổi**, không chỉ là có lời gọi `signal`. Nguyên tắc chờ và thức dậy giả được quy định trong [Condition — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/Condition.html).

## 5. signal khác signalAll như thế nào?

| Lời gọi | Tác động lên nhóm chờ | Điều nó không làm |
| --- | --- | --- |
| `signal()` | Chọn một luồng đang chờ trên condition đó để đánh thức | Không chọn tùy ý một luồng ở condition khác, không nhả khóa của bên gọi |
| `signalAll()` | Đánh thức tất cả luồng đang chờ trên condition đó | Không cho tất cả cùng sở hữu khóa, không bảo đảm mọi điều kiện đều đúng |

Luồng phát tín hiệu vẫn giữ khóa cho đến khi nhả. Các luồng được đánh thức phải tranh quyền lấy lại khóa; chúng không chạy ngay bên trong vùng tới hạn của bên phát.

Với condition của `ReentrantLock`, các luồng chờ được báo theo FIFO, nhưng thứ tự lấy lại khóa phụ thuộc chính sách khóa và lịch chạy. Không biến thứ tự được báo thành cam kết thứ tự hoàn tất nghiệp vụ.

### Khi signal có thể đủ

Nếu các waiter trong cùng nhóm đợi cùng một điều kiện và một lần thay đổi chỉ tạo đúng một cơ hội, đánh thức một luồng có thể phù hợp. Ví dụ thêm một phần tử vào hộp thư một chỗ tạo một cơ hội cho consumer; lấy phần tử đó ra tạo một chỗ cho producer.

Thiết kế vẫn cần tính tới mọi đường làm trạng thái thay đổi và cách xử lý hủy. Không chọn `signal` chỉ để giảm số lần đánh thức khi chưa chứng minh đúng nhóm waiter sẽ có thể tiến triển.

### Khi cần cân nhắc signalAll

Một thay đổi đóng/dừng có thể làm tất cả waiter cần kiểm tra lại để thoát. Hoặc cùng một condition đang chứa những luồng đợi các biểu thức khác nhau, nên chọn một luồng không phù hợp có thể không tạo tiến triển. `signalAll` giúp mọi bên kiểm tra lại, đổi lại nhiều luồng có thể cùng thức rồi phần lớn lại phải chờ.

Nếu có nhiều điều kiện độc lập, cân nhắc tách condition thay vì gom tất cả vào một nhóm rồi dựa hoàn toàn vào đánh thức hàng loạt.

## 6. Tín hiệu không phải một quyền chờ được tích trữ

Gọi `signal()` khi không có waiter không tạo một phiếu đánh thức để một waiter tương lai dùng lại. Nếu cần ghi nhớ sự kiện, trạng thái dữ liệu phải ghi nhớ điều đó.

Ví dụ producer đặt `slot=value` dưới khóa rồi phát tín hiệu. Nếu chưa có consumer chờ, tín hiệu có thể không đánh thức ai; consumer đến sau vẫn thấy `slot != null`, không gọi `await` và nhận dữ liệu. Dữ liệu được giữ trong `slot`, không phải trong tín hiệu.

Đây cũng là lý do phải thay trạng thái và phát tín hiệu dưới cùng giao thức khóa. Nếu kiểm tra ngoài khóa hoặc tách rời nhả khóa–đăng ký chờ bằng cách thủ công, có thể tạo khoảng trống khiến thông báo đi qua trước khi luồng thực sự chờ.

## 7. Chương trình chạy đầy đủ: hộp thư một chỗ có đóng

Ví dụ minh họa một giao thức nhỏ: `put` đợi có chỗ; `take` đợi có dữ liệu; `close` ngừng nhận thêm và cho phép consumer lấy hết dữ liệu đã nhận trước khi kết thúc. `Optional.empty()` là tín hiệu đóng và đã rỗng do lớp ví dụ tự định nghĩa.

Đây là mã học cơ chế `Condition`. Với hàng đợi sản xuất–tiêu thụ thông thường, nên đánh giá `BlockingQueue` có sẵn trước khi tự xây. Các lớp có sẵn và giao thức đóng của ví dụ không có cùng API.

Lưu vào `ConditionSignalDemo.java`:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class ConditionSignalDemo {
    static final class Mailbox {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition notEmpty = lock.newCondition();
        private final Condition notFull = lock.newCondition();
        private String slot;
        private boolean closed;

        void put(String value) throws InterruptedException {
            Objects.requireNonNull(value);
            lock.lockInterruptibly();
            try {
                while (slot != null && !closed) {
                    notFull.await();
                }
                if (closed) {
                    throw new IllegalStateException("Mailbox is closed");
                }
                slot = value;
                notEmpty.signal();
            } finally {
                lock.unlock();
            }
        }

        Optional<String> take() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (slot == null && !closed) {
                    notEmpty.await();
                }
                if (slot == null) {
                    return Optional.empty();
                }
                String value = slot;
                slot = null;
                notFull.signal();
                return Optional.of(value);
            } finally {
                lock.unlock();
            }
        }

        void close() {
            lock.lock();
            try {
                closed = true;
                notEmpty.signalAll();
                notFull.signalAll();
            } finally {
                lock.unlock();
            }
        }
    }

    private static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected mailbox result");
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Mailbox mailbox = new Mailbox();
        List<String> received =
                Collections.synchronizedList(new ArrayList<>());

        Runnable consume = () -> {
            try {
                while (true) {
                    Optional<String> next = mailbox.take();
                    if (next.isEmpty()) {
                        return;
                    }
                    received.add(next.orElseThrow());
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        Thread first = new Thread(consume, "first");
        Thread second = new Thread(consume, "second");
        first.start();
        second.start();

        mailbox.put("B");
        mailbox.put("A");
        mailbox.close();

        first.join();
        second.join();

        List<String> sorted = new ArrayList<>(received);
        Collections.sort(sorted);
        check(sorted.equals(List.of("A", "B")));
        System.out.println("received: " + sorted);
        System.out.println("consumers stopped: true");
        System.out.println("closed and drained: " + mailbox.take().isEmpty());

        try {
            mailbox.put("C");
            throw new AssertionError("Closed mailbox must reject writes");
        } catch (IllegalStateException expected) {
            System.out.println("put after close: IllegalStateException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ConditionSignalDemo.java
java ConditionSignalDemo
```

Stdout:

```text
received: [A, B]
consumers stopped: true
closed and drained: true
put after close: IllegalStateException
```

Producer là main, còn hai consumer đều gọi `take` trong vòng lặp. Mỗi lần đặt một giá trị, `notEmpty.signal()` báo một consumer; mỗi lần lấy ra, `notFull.signal()` báo một producer có thể chờ chỗ.

`close()` đặt `closed=true` và gọi `signalAll()` trên cả hai nhóm. Consumer đang đợi dữ liệu phải kiểm tra lại để biết có cần thoát; producer đang đợi chỗ phải biết không được gửi tiếp. Nếu chỉ báo một waiter khi đóng, những waiter còn lại có thể không có thay đổi nào khác để thức dậy.

`take()` chỉ trả `Optional.empty()` khi `slot` rỗng và `closed` đã đúng. Nếu đóng trong lúc còn dữ liệu, nó vẫn trả dữ liệu đó trước; vòng gọi tiếp theo mới thấy đóng và rỗng. Đó là lựa chọn kết thúc có xả hết việc của lớp ví dụ.

Không cần đoán một consumer đã kịp chờ hay chưa bằng `sleep`. Nếu dữ liệu tới trước, trạng thái giúp consumer đến sau nhận ngay; nếu consumer chờ trước, tín hiệu tạo cơ hội lấy lại khóa.

Thứ tự xử lý xong giữa hai consumer có thể khác nhau. Chương trình chỉ sắp xếp kết quả sau `join()` cả hai luồng để stdout ổn định, không khẳng định tác vụ đã hoàn tất theo thứ tự B rồi A.

## 8. Ngắt và giới hạn thời gian chờ

`await()` có thể ném `InterruptedException`, đồng thời xóa cờ ngắt theo hợp đồng. Với condition từ `ReentrantLock`, sau một lần chờ hợp lệ, khóa được lấy lại trước khi ngoại lệ được chuyển về bên gọi, nên `finally` có thể nhả quyền giữ của phạm vi tương ứng.

Trong ví dụ, các phương thức `put` và `take` chuyển ngoại lệ lên; `Runnable` của consumer khôi phục cờ ngắt rồi kết thúc. Không bắt rồi tiếp tục lấy dữ liệu khi điều kiện chưa đúng.

Việc lấy khóa ban đầu và việc chờ condition là hai điểm khác nhau. `lock.lockInterruptibly()` làm cả giai đoạn lấy khóa ban đầu có thể hủy bằng ngắt; dùng `lock.lock()` rồi `await()` chỉ làm giai đoạn chờ condition có ngắt theo API đó.

Khi dùng chờ có thời hạn trong vòng lặp, không đặt lại toàn bộ thời hạn sau mỗi lần thức dậy giả. Có thể truyền tiếp ngân sách còn lại do `awaitNanos` trả về:

```java
// Đoạn minh họa trong phương thức throws InterruptedException.
long remaining = unit.toNanos(timeout);
lock.lockInterruptibly();
try {
    while (!ready) {
        if (remaining <= 0L) {
            return false;
        }
        remaining = changed.awaitNanos(remaining);
    }
    return true;
} finally {
    lock.unlock();
}
```

Đoạn này chỉ quản lý ngân sách chờ condition, không tính thời gian chờ lấy khóa ban đầu. Nếu cần hạn cho toàn bộ phương thức, phải thiết kế ngân sách chung cho cả hai giai đoạn và xử lý theo yêu cầu. Hết thời gian cũng không có nghĩa toàn bộ lời gọi trở lại đúng một mốc đồng hồ, vì luồng còn phải lấy lại khóa và được lập lịch chạy.

`awaitUninterruptibly()` là biến thể khác, không dùng ngoại lệ ngắt để bỏ chờ; không thay vào chỉ để tránh viết xử lý `InterruptedException`, vì nó thay đổi khả năng hủy của tác vụ.

## 9. Những lỗi cần tránh

- Dùng `if` thay `while` rồi tin rằng được báo đồng nghĩa điều kiện đúng.
- Gọi `signal` ngoài khóa hoặc trên condition không cùng giao thức dữ liệu.
- Cho rằng `signal` tự nhả khóa hoặc chuyển quyền sở hữu trực tiếp.
- Gọi tín hiệu nhưng không lưu trạng thái cho những luồng đến sau.
- Dùng `Thread.sleep` khi đang giữ khóa để đợi bên khác sửa dữ liệu.
- Chỉ báo một luồng khi một thay đổi vòng đời yêu cầu mọi waiter thoát.
- Nuốt yêu cầu ngắt rồi tiếp tục vòng chờ vô hạn.
- Giữ một khóa khác khiến bên có thể làm điều kiện đúng không chạy được.

## 10. Tự kiểm tra

1. `signal()` có nhả khóa của luồng gọi không? Không.
2. Sau khi được báo, waiter có chạy ngay mà không cần lấy lại khóa không? Không; nó phải lấy lại.
3. Vì sao `await` nằm trong `while`? Vì điều kiện có thể chưa đúng sau khi thức dậy, do thức dậy giả hoặc luồng khác thay trạng thái.
4. Gọi `signal` lúc chưa ai chờ có tích trữ một tín hiệu cho tương lai không? Không; trạng thái ứng dụng phải lưu điều cần nhớ.
5. Có hai condition trên một lock; `signalAll` một condition có đánh thức waiter của condition kia không? Không.
6. Đóng một hộp thư có nhiều waiter nên xử lý thế nào? Đổi trạng thái đóng dưới khóa và đánh thức đầy đủ các nhóm cần kiểm tra lại theo giao thức.
