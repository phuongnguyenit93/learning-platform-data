# Nhiều Condition dùng chung một Lock

## 1. Một trạng thái chung có thể tạo ra nhiều lý do phải chờ

Một bộ đệm có giới hạn có ít nhất hai nhóm luồng: bên muốn thêm chờ khi đầy, bên muốn lấy chờ khi rỗng. Một bộ quản lý tài nguyên cũng có thể có nhóm chờ mượn tài nguyên và nhóm chờ mọi tài nguyên được trả lại để đóng hệ thống.

Các nhóm ấy cùng đọc/ghi một trạng thái liên quan, nên thường cần chung một khóa bảo vệ. Tuy nhiên, chúng không nhất thiết cần chung một tập luồng chờ. `Condition` cho phép tạo nhiều tập chờ gắn với cùng một `Lock`, giúp thông báo đúng nhóm khi trạng thái thay đổi.

Trong bài, `ReentrantLock` bảo vệ dữ liệu và các `Condition` do nó tạo quản lý việc chờ. Đây vẫn là cơ chế hiện hành trong Java; chương trình minh họa dùng Java 17 trở lên.

## 2. Mô hình đúng: một khóa, nhiều tập chờ

```java
// Đoạn khai báo trong một lớp.
private final ReentrantLock lock = new ReentrantLock();
private final Condition notEmpty = lock.newCondition();
private final Condition notFull = lock.newCondition();
```

Mỗi lần `newCondition()` tạo một condition riêng gắn với `lock`. Các luồng đang chờ `notEmpty` không đồng thời là waiter của `notFull` chỉ vì hai condition dùng cùng khóa.

```text
Trạng thái chung được bảo vệ bởi lock
                |
                +-- notEmpty: nhóm đợi có dữ liệu
                |
                +-- notFull:  nhóm đợi có chỗ

Tất cả nhóm dùng cùng quyền loại trừ khi kiểm tra/thay trạng thái.
Mỗi nhóm có điểm chờ và tín hiệu riêng.
```

Nhiều condition không tạo nhiều khóa độc lập. Khi một luồng đang giữ `lock`, các luồng khác cần cùng `lock` vẫn phải chờ, bất kể chúng quan tâm condition nào. Lợi ích là phân loại thông báo, không phải cho các nhóm tùy ý sửa chung dữ liệu cùng lúc.

Cách tách tập chờ được nêu trong [Condition — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/Condition.html).

## 3. Gắn mỗi condition với một biểu thức trạng thái

Tên condition không tự kiểm tra dữ liệu. Ứng dụng phải viết biểu thức mà mỗi nhóm chờ quan tâm:

| Nhóm trong bộ đệm | Chờ khi | Sau thay đổi nào có thể tiếp tục? | Condition thường dùng |
| --- | --- | --- | --- |
| Bên thêm | `count == capacity` | Một phần tử được lấy ra | `notFull` |
| Bên lấy | `count == 0` | Một phần tử được thêm vào | `notEmpty` |

Một chuyển tiếp “thêm thành công” thường báo `notEmpty`; “lấy thành công” thường báo `notFull`. Nếu báo nhầm nhóm, vẫn có thể không ném ngoại lệ vì condition cùng gắn với khóa, nhưng hệ thống có thể không tiến triển.

Mọi lần đọc/ghi `count`, `capacity` liên quan và trạng thái vòng đời phải tuân theo cùng giao thức bảo vệ. Chỉ tạo condition từ đúng lock không cứu được dữ liệu đang bị sửa ngoài khóa.

## 4. Mẫu await cho từng nhóm

```java
// Đoạn khung minh họa trong phương thức throws InterruptedException.
lock.lockInterruptibly();
try {
    while (!predicateForThisGroup()) {
        conditionForThisGroup.await();
    }
    // Thay đổi trạng thái được bảo vệ.
    conditionForAffectedGroup.signal();
} finally {
    lock.unlock();
}
```

`await()` nhả chính khóa gắn với condition trong cơ chế chờ, cho phép các luồng khác thay trạng thái. Trước khi trả về bình thường, nó lấy lại khóa. Với condition của `ReentrantLock`, mức tái nhập được khôi phục khi lấy lại.

Luôn kiểm tra bằng `while`: một luồng khác có thể dùng mất cơ hội trước khi waiter lấy lại khóa; nền tảng cũng cho phép thức dậy giả. “Được báo” chỉ là cơ hội kiểm tra lại, không phải xác nhận điều kiện luôn đúng.

Không dùng `Thread.sleep` trong lúc giữ khóa để đợi nhóm khác làm thay đổi trạng thái. Nó không nhả khóa và có thể chặn chính bên cần chạy. Cũng không nhả khóa thủ công rồi mới đăng ký chờ, vì có thể tạo khoảng trống bỏ lỡ thông báo.

## 5. signal theo nhóm; signalAll khi mọi waiter cần kiểm tra lại

`a.signal()` chỉ chọn waiter đang chờ trên condition `a`, không chọn waiter của `b`. `a.signalAll()` cũng chỉ báo tất cả waiter của `a`. Nếu một thay đổi ảnh hưởng cả hai nhóm, phải xử lý thông báo cho cả hai nhóm theo giao thức.

Ví dụ đóng bộ đệm có thể khiến cả producer lẫn consumer cần thoát hoặc xử lý phần còn lại. Chỉ `notEmpty.signalAll()` chưa đủ cho producer đang nằm chờ ở `notFull`.

Việc phát tín hiệu không nhả khóa của bên gọi. Các waiter sau khi được báo phải lấy lại cùng khóa, nên chúng không cùng chạy đồng thời trong vùng được bảo vệ.

`signal` thường thích hợp khi một chuyển tiếp chỉ tạo một cơ hội cho các waiter cùng loại. `signalAll` phù hợp khi một điều kiện hoàn tất cho phép nhiều waiter cùng đạt mục đích, hoặc một sự kiện vòng đời yêu cầu tất cả kiểm tra lại. Đánh thức nhiều luồng có chi phí, nhưng đánh thức quá ít có thể làm chương trình đứng lại.

## 6. Ví dụ khác bộ đệm: chờ mượn và chờ trả hết

Xét một lớp quản lý số quyền sử dụng tài nguyên. Nó không chứa tài nguyên thật mà chỉ đếm số quyền đang được dùng:

```text
0 <= inUse <= capacity

Chưa đóng và inUse < capacity:
    có thể cấp một quyền mới.

Đã đóng:
    không cấp thêm; các quyền đã cấp vẫn phải được trả.

inUse == 0:
    mọi quyền đã được trả, các bên đợi đóng có thể hoàn tất.
```

Hai nhóm chờ dùng hai condition:

| Condition | Nhóm sử dụng | Điều cần kiểm tra |
| --- | --- | --- |
| `permitAvailable` | Bên muốn nhận quyền | Có chỗ hoặc hệ thống đã đóng để báo từ chối |
| `allReturned` | Bên đóng và đợi thu hồi hết | `inUse == 0` |

Một lần trả tạo một chỗ nên báo một bên đợi nhận. Nếu số đang dùng về 0, mọi bên đợi “đã trả hết” có thể tiếp tục, nên báo tất cả nhóm đó. Khi đóng, mọi bên đợi nhận quyền cần biết không được nhận nữa.

## 7. Chương trình chạy đầy đủ

Lưu thành `MultipleConditionsDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantLock;

public class MultipleConditionsDemo {
    static final class PermitPool {
        private final ReentrantLock lock = new ReentrantLock();
        private final Condition permitAvailable = lock.newCondition();
        private final Condition allReturned = lock.newCondition();
        private final int capacity;
        private int inUse;
        private boolean closed;

        PermitPool(int capacity) {
            if (capacity <= 0) {
                throw new IllegalArgumentException("capacity must be positive");
            }
            this.capacity = capacity;
        }

        void acquire() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                while (inUse == capacity && !closed) {
                    permitAvailable.await();
                }
                if (closed) {
                    throw new IllegalStateException("Pool is closed");
                }
                inUse++;
            } finally {
                lock.unlock();
            }
        }

        void release() {
            lock.lock();
            try {
                if (inUse == 0) {
                    throw new IllegalStateException("No permit to return");
                }
                inUse--;
                permitAvailable.signal();
                if (inUse == 0) {
                    allReturned.signalAll();
                }
            } finally {
                lock.unlock();
            }
        }

        void closeAndAwaitReturned() throws InterruptedException {
            lock.lockInterruptibly();
            try {
                closed = true;
                permitAvailable.signalAll();
                while (inUse != 0) {
                    allReturned.await();
                }
            } finally {
                lock.unlock();
            }
        }
    }

    private static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected pool result");
        }
    }

    public static void main(String[] args) throws InterruptedException {
        PermitPool pool = new PermitPool(1);
        CountDownLatch acquired = new CountDownLatch(1);
        CountDownLatch mayReturn = new CountDownLatch(1);
        AtomicBoolean returned = new AtomicBoolean(false);
        AtomicBoolean closeCompleted = new AtomicBoolean(false);

        Thread borrower = new Thread(() -> {
            try {
                pool.acquire();
                try {
                    acquired.countDown();
                    mayReturn.await();
                } finally {
                    pool.release();
                    returned.set(true);
                }
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "borrower");

        Thread closer = new Thread(() -> {
            try {
                pool.closeAndAwaitReturned();
                closeCompleted.set(true);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "closer");

        borrower.start();
        acquired.await();
        check(!returned.get());
        System.out.println("permit is in use: true");

        closer.start();
        mayReturn.countDown();
        borrower.join();
        closer.join();

        check(returned.get());
        check(closeCompleted.get());
        System.out.println("permit returned: " + returned.get());
        System.out.println("close completed: " + closeCompleted.get());

        try {
            pool.acquire();
            throw new AssertionError("Closed pool must reject acquisition");
        } catch (IllegalStateException expected) {
            System.out.println("acquire after close: IllegalStateException");
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 MultipleConditionsDemo.java
java MultipleConditionsDemo
```

Stdout:

```text
permit is in use: true
permit returned: true
close completed: true
acquire after close: IllegalStateException
```

`acquired` báo main biết borrower đã nhận quyền. `mayReturn` giữ borrower chưa trả cho đến khi main đã xác nhận có một quyền đang dùng. Sau đó closer có thể chạy trước hoặc sau lần trả thực tế.

Nếu closer tới trước, nó đặt `closed=true`, đánh thức các bên đợi nhận và chờ trên `allReturned`. `await` nhả khóa để borrower có thể vào `release`. Nếu borrower đã trả trước, closer nhìn thấy `inUse==0` và không cần chờ. Cả hai lịch chạy đều đúng và cho cùng stdout.

Chương trình không dùng `sleep` để khẳng định closer đã chờ bên trong condition. Nó kiểm tra kết quả cuối và giao thức dữ liệu; `join()` đợi cả hai tác vụ kết thúc trước khi in các cờ.

`closeAndAwaitReturned()` cấm cấp quyền mới trước khi chờ thu hồi. Nếu không có bước đóng ấy, một bên đợi thu hồi có thể cứ bị việc nhận quyền mới kéo dài thời gian chờ.

Đây là bộ đếm quyền tối giản để học nhiều condition. Nó không theo dõi quyền theo từng đối tượng/luồng, nên bên gọi phải trả đúng một lần sau mỗi lần nhận thành công. Nếu xây bộ quản lý tài nguyên thật, cần cơ chế ngăn trả trùng, xác thực quyền và quản lý tài nguyên lỗi; không coi phép kiểm tra `inUse==0` là đầy đủ cho mọi lỗi sử dụng.

## 8. Vì sao một condition chung với signal có thể sai?

Xét một thiết kế khác có thao tác giám sát “đợi trả hết” mà chưa đóng việc cấp quyền mới, rồi gộp mọi bên vào một nhóm duy nhất:

- Một số luồng đợi có quyền để mượn.
- Một số luồng giám sát đợi mọi quyền được trả hết.

Khi một quyền được trả nhưng vẫn còn quyền đang dùng, chỉ nhóm muốn mượn có thể tiến triển. Nếu một lệnh `signal` chung chọn bên chờ trả hết, bên ấy kiểm tra rồi lại chờ. Bên có thể mượn có thể vẫn ngủ và không còn chuyển tiếp nào khác để báo nó.

Một condition chung kết hợp `signalAll` có thể đúng trong một thiết kế kiểm tra lại đầy đủ, nhưng đánh thức cả những nhóm không liên quan. Tách condition giúp biểu diễn rõ luồng nào cần được báo và giảm số lượt thức không hữu ích.

Không cố suy thứ tự chọn nhóm từ FIFO của waiter để thay cho thiết kế đúng. Thứ tự waiter có thể khác nhau giữa các lần chạy, và thứ tự được báo cũng không bảo đảm thứ tự hoàn tất xử lý.

## 9. Trạng thái mới là điều được ghi nhớ

`signal` hoặc `signalAll` khi chưa có waiter không tạo tín hiệu tích trữ cho tương lai. Đúng giao thức không đòi một waiter tương lai phải nhận lại mọi tín hiệu cũ.

Trong ví dụ, nếu mọi quyền đã trả trước khi closer tới, closer thấy `inUse==0` và hoàn tất. Nó không cần có mặt lúc `allReturned.signalAll()` được gọi. Nếu pool đã đóng, bên nhận tới sau thấy `closed` và bị từ chối mà không cần ai báo lại.

Điều này chỉ đúng khi bước kiểm tra, đăng ký chờ và cập nhật tuân theo cùng khóa. Nếu một luồng đọc trạng thái ngoài khóa rồi mới quyết định chờ, nó có thể dựa vào giá trị cũ và chờ sau khi chuyển tiếp hữu ích đã xảy ra.

## 10. Ngắt, đóng và tài nguyên đã cấp

`acquire` và `closeAndAwaitReturned` trong ví dụ có thể bị ngắt ở lần lấy khóa hoặc ở `await`. Chúng chuyển `InterruptedException` lên bên gọi; tác vụ ngoài khôi phục cờ và kết thúc theo chính sách của ví dụ.

Nếu closer đã đặt `closed=true` rồi bị ngắt trong lúc chờ trả hết, pool vẫn đóng. Hủy lần chờ không tự hoàn tác trạng thái đóng. Bên điều phối phải phân biệt “đã yêu cầu đóng” với “đã xác nhận mọi quyền trả hết”.

Borrower đặt `release()` trong `finally` sau khi nhận thành công, nên bị ngắt trong công việc cũng không tự làm mất quyền đang dùng. Ngược lại, nếu `acquire` bị ngắt trước khi thành công, bên gọi không được trả một quyền mình chưa nhận.

`await` chỉ nhả khóa gắn với condition ấy; nó không nhả mọi tài nguyên hoặc khóa khác của tác vụ. Nếu bên chờ trả hết đang giữ một khóa ngoài mà borrower cần để trả, hệ thống vẫn có thể bế tắc.

Thêm condition không loại bỏ việc thiết kế thứ tự khóa và đường hủy. Hợp đồng quyền sở hữu, nhả/tái lấy và phản hồi ngắt được mô tả trong [ReentrantLock — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html#newCondition()).

## 11. Kiểm tra một thiết kế nhiều condition

Với mỗi condition, viết rõ nhóm waiter và biểu thức cần đợi. Với mỗi thao tác thay trạng thái, xác định những biểu thức nào có thể đổi từ chưa đạt sang đạt, hoặc những waiter nào phải tỉnh để hủy. Từ đó chọn condition cần báo và số waiter cần báo.

Không dựa vào `hasWaiters` hay số waiter ước lượng để chứng minh tính đúng đắn của việc báo. Cũng không tạo condition mới ở mỗi lần gọi rồi chờ trên một đối tượng mà bên phát tín hiệu không dùng cùng đối tượng ấy.

Nếu bài toán đã có công cụ chuyên dụng như hàng đợi có chờ hoặc semaphore, hãy đánh giá công cụ đó trước khi tự quản lý nhiều tập chờ. Nhiều condition hữu ích khi giao thức trạng thái có nhiều loại chờ thật sự, không phải mục tiêu để tăng số đối tượng đồng bộ.

## 12. Tự kiểm tra

1. Hai condition cùng dùng một lock có phải hai khóa bảo vệ độc lập không? Không.
2. `signalAll` trên condition A có báo các waiter của B không? Không.
3. Một waiter được báo có thể bỏ kiểm tra `while` không? Không.
4. Vì sao đóng hệ thống có thể cần báo nhiều condition? Vì nhiều nhóm đợi các lý do khác nhau đều cần kiểm tra trạng thái đóng.
5. Một bên đến sau khi điều kiện đã đúng có cần tín hiệu cũ được giữ lại không? Không; nó kiểm tra trạng thái dưới khóa và có thể không cần chờ.
6. Bị ngắt trong lúc đợi đóng có tự mở hệ thống trở lại không? Không; phải xác định và xử lý riêng những thay đổi đã thực hiện.
