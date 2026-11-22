# ReentrantLock và tính tái nhập

## 1. Khóa để bảo vệ dữ liệu dùng chung

`ReentrantLock` là một khóa loại trừ lẫn nhau (mutual exclusion lock): tại một thời điểm, chỉ một luồng là chủ sở hữu của cùng một đối tượng khóa. Những đoạn mã cùng tuân theo khóa đó có thể bảo vệ dữ liệu dùng chung khỏi việc truy cập xen kẽ không hợp lệ.

Từ “reentrant” nghĩa là tái nhập: luồng đã giữ khóa được phép lấy lại chính khóa ấy, chẳng hạn khi một phương thức đang giữ khóa gọi một phương thức khác cũng có lệnh lấy khóa. Luồng này không phải chờ chính mình nhả khóa trước.

Điều đó hữu ích khi các phương thức công khai hoặc các hàm hỗ trợ có thể được gọi độc lập nhưng cũng có thể gọi lồng nhau. Mỗi phương thức vẫn quản lý cặp lấy–nhả của mình; việc gọi lồng không tự gây bế tắc chỉ vì lấy lại cùng khóa.

`ReentrantLock` vẫn là API hiện hành trong Java. Ví dụ trong bài dùng Java 17 trở lên, tập trung vào quyền sở hữu và tái nhập thay vì phụ thuộc chi tiết triển khai nội bộ.

## 2. Chủ sở hữu và số lần giữ khóa

Một cách mô hình hóa trạng thái khóa là: chủ sở hữu hiện tại cùng số lần luồng đó đã lấy khóa thành công mà chưa nhả tương ứng (hold count).

| Bước | Luồng thực hiện | Trạng thái sau bước |
| --- | --- | --- |
| Ban đầu | Chưa có | Không có chủ, số lần giữ bằng 0 |
| `lock()` lần đầu | A | A là chủ, số lần giữ bằng 1 |
| A gọi `lock()` lần nữa | A | A vẫn là chủ, số lần giữ bằng 2 |
| A gọi `unlock()` một lần | A | A vẫn là chủ, số lần giữ còn 1 |
| B thử lấy khóa lúc này | B | Chưa được quyền giữ vì A chưa nhả hết |
| A gọi `unlock()` lần nữa | A | Số lần giữ về 0, khóa có thể được luồng khác lấy |

Mỗi lần lấy thành công cần đúng một lần `unlock()` tương ứng. Một lần `unlock()` sau hai lần lấy không giải phóng hoàn toàn khóa.

`getHoldCount()` trả số lần giữ của **luồng hiện tại**, không phải số luồng đang chờ hay một bộ đếm chung mà mọi luồng đều thấy giống nhau. Luồng không phải chủ nhận 0. `isHeldByCurrentThread()` kiểm tra quyền sở hữu của chính luồng gọi.

Quy tắc chủ sở hữu và tăng/giảm số lần giữ được mô tả trong [ReentrantLock — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html).

## 3. Mẫu sử dụng phải ghép với finally

```java
// Đoạn minh họa bên trong một phương thức.
lock.lock();
try {
    // Đọc/ghi dữ liệu được bảo vệ bởi lock.
} finally {
    lock.unlock();
}
```

Đặt `try` ngay sau khi đã lấy khóa. Mọi đường rời khỏi khối được bảo vệ, kể cả `return` hoặc ngoại lệ, đều chạy `finally` trong quá trình thoát bình thường của luồng Java.

Không đặt một lệnh có thể ném ngoại lệ giữa `lock()` thành công và khối `try`. Không chỉ nhả khóa ở cuối đường chạy thành công. Với khóa tường minh, JVM không tự nhả chỉ vì phương thức kết thúc như với khối `synchronized`.

Đối với phương thức thử lấy khóa, chỉ nhả nếu lần thử đã thành công:

```java
// Đoạn minh họa bên trong một phương thức.
if (lock.tryLock()) {
    try {
        // Xử lý khi đã lấy được khóa.
    } finally {
        lock.unlock();
    }
} else {
    // Chọn cách xử lý khi chưa lấy được khóa.
}
```

Gọi `unlock()` khi luồng hiện tại không sở hữu khóa làm `ReentrantLock` ném `IllegalMonitorStateException`. Không dùng một luồng khác để “nhả giúp” chủ sở hữu.

## 4. Tái nhập hỗ trợ lời gọi lồng nhau

Giả sử `process()` đã lấy khóa rồi gọi `update()`, và `update()` cũng lấy chính khóa đó. Với `ReentrantLock`, `update()` tăng số lần giữ lên 2; khi nó kết thúc và nhả, số lần giữ quay về 1. Phần còn lại của `process()` vẫn đang được bảo vệ.

Điểm cần chú ý là quyền tái nhập thuộc **cùng luồng** và **cùng đối tượng khóa**. Hai `new ReentrantLock()` khác nhau không tạo thành một vùng bảo vệ chung, dù chúng được đặt tên giống nhau. Ngược lại, luồng khác không được quyền đi vào chỉ vì chủ hiện tại gọi lồng nhiều lần.

Tái nhập cũng không có nghĩa là gọi lại phương thức qua tác vụ bất đồng bộ vẫn giữ nguyên quyền sở hữu. Nếu chuyển việc sang một luồng khác, luồng đó phải tự lấy khóa và có thể phải chờ chủ hiện tại.

## 5. Chương trình chạy đầy đủ

Chương trình sau có một phương thức ngoài lấy khóa rồi gọi một hàm hỗ trợ cũng lấy khóa. Nó kiểm tra số lần giữ, cho một luồng khác thử lấy đúng lúc khóa vẫn thuộc main, và thử tái nhập bằng `tryLock()` từ chính chủ.

Lưu vào `ReentrantLockDemo.java`:

```java
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.ReentrantLock;

public class ReentrantLockDemo {
    private final ReentrantLock lock = new ReentrantLock();
    private int balance;

    private void addUnderOwnLock(int amount) {
        lock.lock();
        try {
            check(lock.getHoldCount() == 2);
            balance += amount;
            System.out.println("inside helper: holds=" + lock.getHoldCount());
        } finally {
            lock.unlock();
        }
    }

    private void execute() throws InterruptedException {
        AtomicBoolean otherAcquired = new AtomicBoolean(true);

        lock.lock();
        try {
            check(lock.getHoldCount() == 1);
            System.out.println("outer entry: holds=" + lock.getHoldCount());

            addUnderOwnLock(5);

            check(lock.getHoldCount() == 1);
            check(lock.isHeldByCurrentThread());
            System.out.println("after helper: holds=" + lock.getHoldCount());

            Thread contender = new Thread(() -> {
                boolean acquired = lock.tryLock();
                otherAcquired.set(acquired);
                if (acquired) {
                    lock.unlock();
                }
            }, "contender");
            contender.start();
            contender.join();
            check(!otherAcquired.get());
            System.out.println("other thread tryLock: " + otherAcquired.get());

            boolean ownTry = lock.tryLock();
            check(ownTry);
            try {
                check(lock.getHoldCount() == 2);
                System.out.println("owner tryLock: " + ownTry
                        + ", holds=" + lock.getHoldCount());
            } finally {
                lock.unlock();
            }
        } finally {
            lock.unlock();
        }

        check(lock.getHoldCount() == 0);
        System.out.println("after outer: holds=" + lock.getHoldCount());
        System.out.println("balance=" + balance);
    }

    private static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected lock state");
        }
    }

    public static void main(String[] args) throws InterruptedException {
        new ReentrantLockDemo().execute();
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ReentrantLockDemo.java
java ReentrantLockDemo
```

Stdout:

```text
outer entry: holds=1
inside helper: holds=2
after helper: holds=1
other thread tryLock: false
owner tryLock: true, holds=2
after outer: holds=0
balance=5
```

Sau khi hàm hỗ trợ nhả, `holds=1` chứng minh phương thức ngoài vẫn giữ khóa. Luồng contender dùng `tryLock()` không thời hạn, nên nó trả `false` khi main đang giữ; nó không chờ main nhả.

Ví dụ `join()` contender trong lúc main giữ khóa chỉ hoạt động được vì contender không chờ khóa: nó thử một lần rồi kết thúc. Nếu đổi contender sang `lock()` và vẫn giữ `join()` ở vị trí ấy, main có thể chờ contender kết thúc trong khi contender chờ main nhả khóa. Không sao chép cấu trúc đợi này sang một tác vụ cần khóa chặn.

Lần `tryLock()` từ chính main trả `true` vì main đã là chủ, và nó vẫn tăng số lần giữ lên 2. Do đó, `tryLock` thành công do tái nhập cũng cần một lần `unlock()` riêng; không được bỏ qua với lý do “đã giữ từ trước”.

Dòng đọc `balance` cuối được thực hiện bởi chính luồng main sau các lần thay đổi của nó; ví dụ không dùng đọc không khóa từ luồng khác để kết luận dữ liệu đã được đồng bộ.

## 6. Tái nhập khác các chế độ lấy khóa

| Phương thức | Khi khóa đang do luồng khác giữ | Khi luồng hiện tại đã giữ khóa |
| --- | --- | --- |
| `lock()` | Chờ lấy được; không phải điểm hủy chờ bằng `InterruptedException` | Lấy lại, tăng số lần giữ |
| `tryLock()` | Thử ngay, có thể trả `false` | Trả `true`, tăng số lần giữ |
| `lockInterruptibly()` | Có thể chờ và phản hồi ngắt bằng `InterruptedException` | Có thể lấy lại nếu không bị ngắt; phương thức ưu tiên phản hồi ngắt theo hợp đồng |
| `tryLock(timeout, unit)` | Chờ có thời hạn hoặc phản hồi ngắt | Có thể lấy lại, nhưng vẫn phải tuân theo ngữ nghĩa ngắt của phương thức |

Không suy rằng mọi phương thức lấy khóa đều hành xử như `lock()` chỉ vì khóa có tính tái nhập. `lockInterruptibly()` có thể ném ngoại lệ ngay khi vào nếu luồng đã có cờ ngắt, kể cả khi nó đang giữ khóa. Nếu lần lấy ấy không thành công, không được nhả thêm một mức giữ mà nó chưa tạo.

`lock()` không tự bỏ chờ chỉ vì luồng nhận yêu cầu ngắt. Nếu nghiệp vụ cần hủy trong lúc chờ, chọn phương thức hỗ trợ đúng khả năng đó và xử lý ngoại lệ. Một thời hạn thử lấy chỉ giới hạn lần chờ lấy khóa, không giới hạn thời gian mã chạy sau khi đã lấy được.

## 7. So với synchronized

`synchronized` cũng có tính tái nhập trên monitor của cùng đối tượng; đây không phải một tính năng chỉ có ở `ReentrantLock`. Một luồng có thể lấy cùng monitor nhiều lần và mỗi lần ra khỏi khối tương ứng giảm một mức giữ. Quy tắc monitor được nêu trong [Java Language Specification, §17.1](https://docs.oracle.com/javase/specs/jls/se21/html/jls-17.html#jls-17.1).

| Khía cạnh | `synchronized` | `ReentrantLock` |
| --- | --- | --- |
| Tái nhập | Có | Có |
| Cách nhả thông thường | Tự nhả khi rời khối/phương thức đồng bộ | Gọi `unlock`, thường trong `finally` |
| Thử lấy ngay bằng API | Không có API tương đương trực tiếp trên khối | `tryLock()` |
| Chờ lấy có ngắt/thời hạn | Không có API tương đương trực tiếp trên khối | `lockInterruptibly`, timed `tryLock` |
| Chờ theo điều kiện | `wait`/`notify` trên monitor | `Condition` gắn với lock |

Không chọn `ReentrantLock` chỉ vì nghĩ `synchronized` không tái nhập hoặc mặc định chậm hơn. Khi không cần các khả năng điều khiển mở rộng, khối đồng bộ có lợi ở cách quản lý phạm vi tự nhả. Quyết định hiệu năng phải dựa trên tải và JVM đang sử dụng.

Cũng không trộn `synchronized(lock)` với `lock.lock()` để bảo vệ cùng dữ liệu rồi cho rằng đó là cùng một khóa. Monitor của đối tượng `lock` và cơ chế của `ReentrantLock` không có quan hệ phối hợp được hợp đồng quy định. Xem [Lock — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/Lock.html).

## 8. Loại trừ và công bố dữ liệu

Mọi đường truy cập dữ liệu cần được bảo vệ phải tuân theo cùng giao thức khóa. Một luồng lấy khóa để ghi không đủ nếu luồng khác đọc dữ liệu dùng chung mà không có cơ chế đồng bộ thích hợp.

Lần nhả khóa và lần lấy thành công tiếp theo của luồng khác trên cùng khóa tạo quan hệ công bố dữ liệu theo hợp đồng đồng bộ bộ nhớ. Luồng đọc đúng cách có thể thấy các thay đổi được hoàn tất trước khi bên ghi nhả.

Nhả một mức từ 2 xuống 1 chưa trao quyền sở hữu cho luồng khác. Không suy từ một lần `unlock` nội bộ rằng mọi luồng đang chờ đã được đi vào. Phải về 0 mới giải phóng hoàn toàn quyền loại trừ của chủ.

`isLocked()`, `getHoldCount()` hay thông tin hàng đợi chờ có ích để quan sát/chẩn đoán, nhưng không thay cho thao tác lấy khóa. Kiểm tra `!isLocked()` rồi đọc dữ liệu vẫn có khoảng trống để luồng khác lấy khóa trước.

## 9. Tái nhập không ngăn mọi deadlock hoặc lỗi gọi lồng

### Hai khóa khác nhau vẫn có thể tạo vòng chờ

Nếu luồng A giữ L1 rồi chờ L2 trong khi luồng B giữ L2 rồi chờ L1, tính tái nhập của từng khóa không phá vòng chờ ấy. Cần thứ tự lấy khóa thống nhất hoặc một thiết kế tránh chu trình phụ thuộc.

### Callback có thể quay lại khi trạng thái chưa hoàn chỉnh

Tái nhập cho phép cùng luồng đi vào lại, nhưng không tự bảo đảm dữ liệu đang ở trạng thái hợp lệ tại mọi điểm trong phương thức. Nếu đang cập nhật dở rồi gọi callback bên ngoài, callback quay lại API trên cùng luồng có thể thấy trạng thái chưa hoàn chỉnh vì nó được phép tái nhập.

Vì vậy, cần bảo vệ cả bất biến dữ liệu và điểm gọi ra bên ngoài, không chỉ bảo đảm cân bằng `lock`/`unlock`. Tránh giữ khóa khi gọi mã không kiểm soát nếu có thể thiết kế khác.

### Thiếu nhả vẫn khóa các luồng khác

Nếu lấy hai lần nhưng chỉ nhả một lần, phương thức có thể đã trả về mà khóa vẫn thuộc luồng cũ. Việc luồng đó kết thúc không phải cơ chế tự giải phóng `ReentrantLock` bị quên nhả. Ghép mỗi lần lấy thành công với `finally` ngay tại phạm vi tương ứng giúp kiểm soát điều này.

Không dùng vòng `while (lock.isHeldByCurrentThread()) lock.unlock()` để che giấu số mức giữ chưa hiểu rõ: cách đó có thể nhả cả quyền giữ thuộc tầng gọi bên ngoài. Mỗi tầng nên nhả đúng mức mình đã lấy.

## 10. Quan hệ với Condition

`Condition` được tạo từ một lock và dùng để chờ một điều kiện của dữ liệu. Nó khác với tái nhập: tái nhập là lấy lại khóa đang sở hữu, còn chờ điều kiện là tạm nhường khả năng tiến triển cho luồng khác rồi lấy lại khóa trước khi tiếp tục.

Với `Condition` do `ReentrantLock` tạo, một lời gọi `await` đúng quyền sở hữu giải phóng các mức giữ trong lúc chờ và khôi phục mức giữ trước đó khi lấy lại khóa. Đây là hợp đồng riêng của thao tác chờ; không thay bằng một `unlock` tùy ý rồi mong số mức giữ tự phục hồi.

Khi viết chờ điều kiện, cần hiểu vòng kiểm tra điều kiện, ngắt và đánh thức. Tính tái nhập không làm mất nhu cầu kiểm tra lại điều kiện sau khi được đánh thức.

## 11. Tự kiểm tra

1. Cùng một luồng gọi `lock()` hai lần trên cùng `ReentrantLock` có phải chờ chính mình không? Không; số lần giữ tăng lên 2.
2. Sau đó chỉ gọi `unlock()` một lần thì luồng khác đã được lấy chưa? Chưa; số lần giữ còn 1.
3. `tryLock()` do chính chủ gọi thành công có cần nhả thêm không? Có; nó cũng tạo thêm một mức giữ.
4. Một luồng khác có thể gọi `unlock()` để nhả giúp chủ không? Không; nó không có quyền sở hữu và gặp `IllegalMonitorStateException`.
5. `synchronized` có tái nhập không? Có.
6. Tái nhập có tự giải quyết vòng chờ giữa hai khóa khác nhau không? Không.
