# ConditionObject và điều kiện hỗ trợ của bộ đồng bộ

## Khái niệm: chờ điều kiện trong khi vẫn bảo vệ dữ liệu

Một khóa chỉ trả lời câu hỏi ai được truy cập dữ liệu chung. Nó chưa trả lời câu hỏi phải làm gì khi dữ liệu chưa sẵn sàng. Ví dụ, luồng đọc đã giữ khóa của một hộp dữ liệu nhưng hộp vẫn rỗng. Nếu nó giữ nguyên khóa rồi chờ, luồng ghi không thể vào để đặt dữ liệu; nếu tự nhả khóa rồi ngủ, việc phối hợp kiểm tra và thông báo lại có thể sai.

`Condition` biểu diễn cơ chế chờ gắn với một khóa. `AbstractQueuedSynchronizer.ConditionObject` là một triển khai `Condition` để người xây công cụ dựa trên AQS sử dụng khi bộ đồng bộ thỏa hợp đồng cần thiết. Trong ứng dụng thông thường, ta lấy `Condition` từ `ReentrantLock.newCondition()` thay vì tự tạo lớp khóa. [Condition](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/Condition.html)

Phải phân biệt **đối tượng điều kiện** với **biểu thức điều kiện nghiệp vụ**. `changed` có thể là đối tượng dùng để chờ/báo, còn `box.ready` mới là điều kiện quyết định được đọc hộp hay chưa. `signal()` không tự đặt `box.ready = true`.

Trình tự sử dụng đúng có ba phần: giữ khóa để kiểm tra dữ liệu; nếu chưa đủ điều kiện thì chờ theo giao thức condition; sau khi lấy lại khóa, kiểm tra điều kiện một lần nữa.

## Vì sao không chỉ nhả khóa rồi ngủ?

Giả sử bên đọc kiểm tra `ready == false`, nhả khóa rồi mới chuẩn bị ngủ. Trong khoảng đó bên ghi có thể đặt dữ liệu và gửi tín hiệu khi bên đọc chưa đăng ký chờ. Nếu bên đọc sau đó ngủ mà không kiểm tra lại hoặc đăng ký đúng cách, nó có thể không có tín hiệu tiếp theo để thức.

Một giao thức condition gắn việc vào hàng đợi điều kiện với việc nhả khóa. Khi mọi bên kiểm tra/cập nhật dữ liệu bằng cùng khóa và dùng condition đúng cách, không cần tự ghép một biến cờ, một lệnh nhả khóa và một lần park rời rạc.

```text
Giữ khóa -> kiểm tra điều kiện nghiệp vụ
    điều kiện đúng -> sử dụng dữ liệu dưới khóa
    điều kiện sai -> await: nhả khóa và chờ
                         -> lấy lại khóa
                         -> kiểm tra lại điều kiện
```

`ConditionObject` vẫn là API hiện hành. Điều cần học là hợp đồng chờ/nhả/lấy lại và quyền sở hữu, không phải một sơ đồ trường nội bộ chỉ đúng với một phiên bản JDK.

## Bộ đồng bộ phải đáp ứng những gì?

Việc một lớp mở rộng AQS chưa đủ để nó hỗ trợ `ConditionObject`. Hợp đồng AQS yêu cầu nền tảng **độc quyền**, nhận biết đúng luồng đang giữ và có thể nhả hoàn toàn rồi khôi phục trạng thái đã lưu. [Điều kiện sử dụng ConditionObject trong AQS](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.html)

| Điều kiện hỗ trợ | Ý nghĩa thực tế | Sai nếu chỉ làm cho có |
| --- | --- | --- |
| `isHeldExclusively()` đúng với luồng hiện tại | Xác định chính bên gọi có quyền độc quyền không | Chỉ kiểm tra `state != 0` sẽ nhầm khóa đang do luồng khác giữ là mình giữ |
| `release(savedState)` nhả hoàn toàn | Bên khác có thể lấy khóa và thay đổi điều kiện | Chỉ nhả một mức của khóa tái nhập khiến bên ghi vẫn bị chặn |
| `acquire(savedState)` có thể khôi phục trạng thái cũ | Khi tiếp tục, luồng giữ quyền như trước khi chờ | Luôn khôi phục về một mức làm mất số lần tái nhập |
| Quy tắc trạng thái có đồng bộ đúng | Dữ liệu nghiệp vụ nhìn thấy theo quan hệ khóa | Một biến chủ sở hữu thông thường không thay thế cập nhật trạng thái nguyên tử |

Với khóa có thể tái nhập hai lần, trạng thái lưu có thể là `2`. Khi chờ, bộ đồng bộ phải xử lý nhả **hai** lần giữ cùng lúc; khi trở lại, nó phải lấy lại **hai** lần giữ. Do đó các móc `tryAcquire(int)` / `tryRelease(int)` không được giả định đối số luôn bằng `1` nếu khóa đó xuất ra condition.

`isHeldExclusively()` không được gọi để hỏi có *bất kỳ* luồng nào giữ khóa; nó hỏi quyền của **luồng hiện tại**. Các phương thức theo dõi chủ sở hữu của `AbstractOwnableSynchronizer` giúp biểu diễn thông tin này, nhưng tự chúng không tạo truy cập `volatile` hay tự làm việc lấy khóa an toàn. [AbstractOwnableSynchronizer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractOwnableSynchronizer.html)

Một bộ đồng bộ chia sẻ thuần túy như kho giấy phép không mặc nhiên đáp ứng hợp đồng trên. Với `ReentrantReadWriteLock`, chỉ khóa ghi hỗ trợ condition; `readLock().newCondition()` không được hỗ trợ. Điều đó phù hợp với việc chờ condition cần dựa trên quyền độc quyền được nhả và lấy lại. [Điều kiện của khóa đọc/ghi](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html)

## Hai hàng đợi có vai trò khác nhau

Hàng đợi condition chứa các luồng đã nhả khóa để chờ một điều kiện. Hàng đợi đồng bộ của AQS chứa các yêu cầu đang tranh quyền lấy khóa. Với `ConditionObject`, `signal()` chuyển một bên chờ phù hợp từ hàng đợi condition sang quá trình chờ giành khóa; nó không giao ngay khóa.

Trình tự minh họa của một lần chờ bình thường:

1. T1 đang giữ khóa, thấy dữ liệu chưa sẵn sàng và gọi `await()`.
2. Cơ chế condition lưu trạng thái, đăng ký chờ và giải phóng hoàn toàn khóa.
3. T2 lấy khóa, cập nhật dữ liệu rồi gọi `signal()` trong khi còn giữ khóa.
4. T1 có cơ hội đi vào quá trình giành lại khóa, nhưng T2 vẫn giữ quyền cho đến khi nhả.
5. T1 lấy lại khóa với trạng thái đã lưu, trở về từ `await()` và kiểm tra lại dữ liệu.

Đây là cách nhìn giao thức, không phải lời hứa thứ tự từng bước cấp CPU. `signalAll()` chuyển mọi bên chờ condition sang quá trình giành khóa; với khóa độc quyền, các luồng ấy vẫn không đồng thời sở hữu khóa. [Cơ chế ConditionObject](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.ConditionObject.html)

Có thể tạo nhiều condition gắn cùng một khóa, chẳng hạn `notEmpty` và `notFull`. Chúng có các nhóm chờ khác nhau. Bên chờ và bên báo phải dùng đúng **cùng một đối tượng condition**; gọi `newCondition()` lần nữa rồi báo trên đối tượng mới không báo cho hàng đợi cũ.

## Minh chứng: nhả toàn bộ và khôi phục hai mức tái nhập

Ví dụ Java 17+ sau tự xây một khóa tối giản để lộ rõ ba móc hỗ trợ `ConditionObject`. Đây là mã học cơ chế: chưa cung cấp toàn bộ giao diện `Lock`, tùy chọn công bằng, API lấy khóa có ngắt/thời hạn hoặc thiết kế tuần tự hóa để dùng như một thư viện. Khi làm ứng dụng, ưu tiên `ReentrantLock` đã có sẵn.

Quy tắc khóa minh họa: `state == 0` là rảnh; số dương là số lần giữ; chỉ chủ sở hữu được tăng số lần giữ hoặc nhả. Mỗi `lock()` thông thường thêm một lần giữ, nhưng đường condition được phép đưa toàn bộ trạng thái đã lưu vào thao tác acquire/release.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.AbstractQueuedSynchronizer;
import java.util.concurrent.locks.Condition;

public class ConditionObjectDemo {
    static final class DemoLock {
        private static final class Sync extends AbstractQueuedSynchronizer {
            @Override
            protected boolean tryAcquire(int amount) {
                Thread current = Thread.currentThread();
                int count = getState();
                if (count == 0) {
                    if (compareAndSetState(0, amount)) {
                        setExclusiveOwnerThread(current);
                        return true;
                    }
                    return false;
                }
                if (getExclusiveOwnerThread() != current) {
                    return false;
                }
                int next = count + amount;
                if (next < 0) {
                    throw new Error("Hold count overflow");
                }
                setState(next);
                return true;
            }

            @Override
            protected boolean tryRelease(int amount) {
                if (!isHeldExclusively()) {
                    throw new IllegalMonitorStateException();
                }
                int next = getState() - amount;
                if (next < 0) {
                    throw new IllegalMonitorStateException();
                }
                if (next == 0) {
                    setExclusiveOwnerThread(null);
                }
                setState(next);
                return next == 0;
            }

            @Override
            protected boolean isHeldExclusively() {
                return getState() != 0
                        && getExclusiveOwnerThread() == Thread.currentThread();
            }

            Condition newCondition() {
                return new ConditionObject();
            }

            int holdCount() {
                return isHeldExclusively() ? getState() : 0;
            }
        }

        private final Sync sync = new Sync();

        void lock() {
            sync.acquire(1);
        }

        void unlock() {
            sync.release(1);
        }

        Condition newCondition() {
            return sync.newCondition();
        }

        int holdCount() {
            return sync.holdCount();
        }
    }

    static final class Box {
        boolean ready;
        boolean consumed;
        int value;
    }

    public static void main(String[] args) throws InterruptedException {
        DemoLock lock = new DemoLock();
        Condition changed = lock.newCondition();
        CountDownLatch entered = new CountDownLatch(1);
        Box box = new Box();
        int[] restoredCount = new int[1];
        int[] observed = new int[1];

        Thread consumer = new Thread(() -> {
            lock.lock();
            lock.lock();
            try {
                entered.countDown();
                while (!box.ready) {
                    changed.await();
                }
                restoredCount[0] = lock.holdCount();
                observed[0] = box.value;
                box.consumed = true;
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                lock.unlock();
                lock.unlock();
            }
        });
        consumer.start();

        entered.await();
        lock.lock();
        try {
            box.value = 42;
            box.ready = true;
            changed.signal();
            System.out.println("consumedBeforeUnlock=" + box.consumed);
        } finally {
            lock.unlock();
        }

        consumer.join();
        System.out.println("restoredHoldCount=" + restoredCount[0]);
        System.out.println("observed=" + observed[0]);
    }
}
```

Lưu thành `ConditionObjectDemo.java`, rồi chạy bằng JDK 17 trở lên:

```shell
javac ConditionObjectDemo.java
java ConditionObjectDemo
```

Stdout khi chương trình không bị ngắt từ bên ngoài:

```text
consumedBeforeUnlock=false
restoredHoldCount=2
observed=42
```

### Vì sao consumer chắc chắn phải nhả hết khóa?

`consumer` lấy khóa hai lần, gọi `entered.countDown()` khi vẫn đang giữ khóa rồi kiểm tra `ready`. `main` chỉ bắt đầu lấy khóa sau khi latch cho phép. Latch không thay thế khóa hộp dữ liệu; nó chỉ giúp đặt trình tự thí nghiệm.

Nếu `consumer` mới báo latch nhưng chưa kịp vào `await()`, `main` vẫn chưa lấy được khóa. Chỉ sau khi `consumer` nhả hết hai lần giữ, `main` mới vào vùng cập nhật. Vì `ready` ban đầu là `false`, bên đọc phải chờ condition để bên ghi có thể vào; không cần dùng `sleep` để đoán thời điểm.

Khi `main` gọi `signal()`, nó vẫn giữ khóa và in `consumedBeforeUnlock=false`. Bên đọc chưa thể quay về để đặt `consumed = true`. Chỉ sau lần `unlock()` của `main`, consumer mới có thể lấy lại khóa, kiểm tra điều kiện và đọc `42`.

`restoredHoldCount=2` cho thấy đường lấy lại dùng trạng thái đã lưu, không chỉ thực hiện một lần lấy mức `1`. Hai lần `unlock()` trong `finally` vì thế cân bằng đúng hai lần giữ ban đầu.

### Ba móc quan trọng trong mã

- `isHeldExclusively` kết hợp trạng thái khác `0` với việc chủ sở hữu chính là luồng đang gọi.
- `tryRelease(amount)` trừ toàn bộ đối số, chỉ trả `true` khi đã về `0`; đường `await` có thể truyền `amount = 2`.
- `tryAcquire(amount)` có thể chuyển từ `0` lên chính `amount`; do đó đường lấy lại có thể khôi phục `2` ngay khi giành được khóa.

Nhánh tăng số lần giữ chỉ chạy cho chủ sở hữu. Nhánh tranh khóa đang rảnh dùng CAS để tránh hai luồng cùng lấy thành công. Khi nhả hoàn toàn, mã xóa thông tin chủ sở hữu trước khi công bố trạng thái rảnh. Những chi tiết này phối hợp với nhau; không nên chép riêng một dòng `new ConditionObject()` vào một bộ đồng bộ chưa có các bất biến tương ứng.

`box.ready`, `box.value` và `box.consumed` được truy cập dưới cùng khóa. Kết quả ở hai mảng chỉ được `main` đọc sau `consumer.join()`. Việc thấy dữ liệu dựa trên các quan hệ đồng bộ và hoàn tất luồng, không dựa vào thời gian đã trôi qua. [JLS, happens-before](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4.5)

## Bên dùng condition phải giữ hợp đồng nào?

### Giữ đúng khóa và kiểm tra bằng while

`await`, `signal` và `signalAll` của condition này phải được dùng khi bên gọi có quyền độc quyền tương ứng. Dùng sai quyền có thể gây `IllegalMonitorStateException`; việc một luồng khác đang giữ khóa không làm bên gọi trở thành hợp lệ.

Vòng `while (!box.ready)` cần thiết dù chương trình đã có `signal()`: có thể thức dậy không do tín hiệu mong đợi, hoặc một bên khác đã dùng dữ liệu trước khi bên chờ lấy lại khóa. Với một hộp nhiều người lấy, tín hiệu chỉ cho biết nên kiểm tra lại, không đặt riêng một món dữ liệu cho luồng vừa được báo.

`synchronized(changed)` không lấy `DemoLock`, và `changed.wait()` / `changed.notify()` không điều khiển hàng đợi condition của AQS. Đó là cơ chế monitor của chính đối tượng Java, có giao thức khác. [Quan hệ giữa Condition và monitor](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/Condition.html)

### Tín hiệu không phải thông điệp được lưu để nhận sau

Nếu chưa có bên chờ, `signal()` không tích lũy một tín hiệu để lần `await()` kế tiếp tự nhận. Trạng thái nghiệp vụ mới là phần lưu thông tin. Nếu bên ghi đã đặt `ready = true` dưới khóa trước khi bên đọc đến, bên đọc kiểm tra thấy đúng và bỏ qua `await()`.

Cập nhật trạng thái rồi báo tín hiệu trong cùng vùng khóa giúp bên chờ sau khi lấy lại khóa kiểm tra được trạng thái mới. Báo mà không thay đổi điều kiện chỉ làm bên chờ thử lại rồi có thể tiếp tục chờ.

### Chọn signal hay signalAll theo nhóm chờ

`signal()` phù hợp khi biết một bên chờ được chọn là đủ và sẽ có khả năng đáp ứng giao thức; `signalAll()` hữu ích khi mọi bên cần kiểm tra lại hoặc có nhiều biểu thức điều kiện cùng dùng chung nhóm chờ. Sau `signalAll`, mỗi bên vẫn phải kiểm tra `while` dưới khóa.

Với các nhóm chờ có mục tiêu khác nhau, có thể dùng các condition riêng để tránh báo sai nhóm. `signalAll()` không sửa được bất biến sai, việc quên cập nhật điều kiện hay lỗi dùng hai khóa khác nhau.

## Ngắt và hết hạn không bỏ qua bước lấy lại khóa

`await()` là điểm chờ có ngắt. Nếu ngắt được phát hiện trước khi vào chờ, nó có thể ném ngay; nếu đã nhả khóa để chờ, cơ chế phải giành lại khóa trước khi hoàn tất việc rời chờ theo hợp đồng. Vì vậy nhánh `finally` của mã đang giữ khóa vẫn có thể nhả quyền đúng số lần. Khi bắt `InterruptedException` mà không truyền lên được, cần kết thúc tác vụ hoặc khôi phục cờ ngắt theo chính sách của chương trình.

`awaitUninterruptibly()` có hợp đồng khác: không kết thúc sớm chỉ vì ngắt và giữ thông tin ngắt để bên gọi xử lý sau. Không nên đổi sang phương thức này chỉ để tránh khai báo `throws`.

Với chờ có hạn, dùng một ngân sách chung và cập nhật phần còn lại qua `awaitNanos`; đặt lại toàn bộ thời hạn sau mỗi lần thức sẽ vô tình kéo dài tổng thời gian chờ. Kết quả hết thời hạn không thay cho kiểm tra trạng thái nghiệp vụ dưới khóa. Ngoài ra, việc lấy lại khóa vẫn có thể khiến thời gian thực tế vượt mốc dự kiến nếu khóa bị giữ lâu. [Các biến thể chờ của ConditionObject](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.ConditionObject.html)

## Lỗi triển khai cần nhận ra

| Lỗi | Hành vi có thể xảy ra | Cách kiểm tra đúng hướng |
| --- | --- | --- |
| `tryRelease` bỏ qua đối số và luôn giảm một | Bên chờ vẫn giữ một phần khóa tái nhập; bên ghi không vào được | Thử await khi đang giữ khóa hai lần |
| `tryAcquire` luôn đặt state thành `1` | Bên chờ trở lại thiếu mức giữ; lần unlock sau có thể sai | Đối chiếu số lần giữ trước/sau await |
| `isHeldExclusively` chỉ trả `state != 0` | Luồng không sở hữu có thể vượt kiểm tra quyền | Thử signal từ một luồng không giữ khóa |
| Dùng `if` thay `while` | Dùng dữ liệu dù biểu thức điều kiện còn sai | Mô hình hóa nhiều bên cùng chờ và cùng tranh dữ liệu |
| Gọi signal trên condition mới tạo | Bên chờ cũ không được báo | Giữ tham chiếu condition dùng chung |
| Bên ghi giữ khóa rồi join bên đang chờ chính khóa đó | Tạo vòng đợi | Chỉ join khi không giữ tài nguyên mà bên được đợi cần lấy |

Để luyện tập, hãy dự đoán ba biến thể: đổi số lần giữ ban đầu từ hai thành ba; gửi tín hiệu nhưng để `ready` vẫn `false`; hoặc đặt dữ liệu sẵn sàng trước khi khởi động consumer. Với biến thể giữ ba lần, phải tăng cả số lần nhả trong `finally`; với tín hiệu mà điều kiện còn sai, vòng `while` vẫn chờ; với dữ liệu đã sẵn sàng, consumer có thể đi tiếp mà không cần await.

Điều kiện để dùng `ConditionObject` nằm ở toàn bộ giao thức của bộ đồng bộ: nhận đúng chủ sở hữu, nhả hết quyền và khôi phục đúng trạng thái. Bên dùng sau đó phải bảo vệ dữ liệu bằng cùng khóa và luôn kiểm tra lại điều kiện nghiệp vụ.
