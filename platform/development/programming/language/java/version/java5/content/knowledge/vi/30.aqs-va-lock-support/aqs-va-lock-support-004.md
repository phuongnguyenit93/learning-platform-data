# Các điểm mở rộng tryAcquire, tryRelease và biến thể shared

## 1. AQS gọi lớp con để quyết định điều gì?

`AbstractQueuedSynchronizer` (AQS) là khung xây dựng bộ đồng bộ. Nó giải quyết phần chờ và cạnh tranh; lớp con cung cấp quy tắc **khi nào một yêu cầu được lấy quyền** và **nhả quyền làm trạng thái thay đổi ra sao**. Các phương thức `tryAcquire`, `tryRelease`, `tryAcquireShared`, `tryReleaseShared` là những điểm mở rộng (hook) nối hai phần đó.

Ví dụ một phòng có một chìa khóa và một khu vực có hai giấy phép vào cửa. Cả hai cần tổ chức người chờ, nhưng điều kiện cấp quyền khác nhau: phòng chỉ có một chủ sở hữu; khu vực cho hai yêu cầu cùng thành công. AQS tái sử dụng cơ chế chờ, còn lớp con diễn đạt quy tắc riêng bằng trạng thái `int`.

Bài học dùng hợp đồng API AQS hiện hành và ví dụ Java 17 trở lên. Mục tiêu là hiểu cách viết điểm mở rộng đúng; không cần học thuộc mã nút hay chi tiết hàng đợi riêng của một bản JDK cũ. Với ứng dụng thông thường, ưu tiên công cụ thư viện như `ReentrantLock` và `Semaphore` thay vì tự xây khóa.

## 2. Phân biệt thao tác công khai với điểm mở rộng

Thiết kế thường có ba tầng:

```text
Ứng dụng gọi phương thức của bộ đồng bộ
    ↓
Lớp bao gọi acquire/release hoặc biến thể shared của AQS
    ↓
AQS gọi tryAcquire/tryRelease hoặc biến thể shared của lớp Sync
```

`Sync` thường là lớp trợ giúp không công khai nằm bên trong lớp bao. Lớp bao định nghĩa API cho người dùng; AQS điều phối việc chờ; lớp `Sync` kiểm tra và cập nhật trạng thái. [Hướng dẫn mở rộng AQS](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.html)

Ví dụ `lock()` gọi `acquire(1)`. AQS có thể gọi `tryAcquire(1)` nhiều lần trước khi lời gọi hoàn thành. Vì thế, `tryAcquire` phải diễn đạt một lần **thử** lấy quyền, không được tự coi lần đầu thất bại là lỗi nghiệp vụ, cũng không được tự gọi lại `acquire` để chờ. Tương tự, `unlock()` cần đi qua `release(1)` để AQS có cơ hội xử lý các yêu cầu đang chờ sau khi trạng thái được nhả.

## 3. Bảng hợp đồng cần nhớ

| Điểm mở rộng | Việc lớp con phải quyết định | Giá trị trả về |
| --- | --- | --- |
| `tryAcquire(int arg)` | Có lấy được quyền độc quyền ngay không? | `true`: đã lấy thành công; `false`: chưa lấy được |
| `tryRelease(int arg)` | Cập nhật việc nhả quyền độc quyền | `true`: đã nhả hoàn toàn; `false`: vẫn chưa nhả hoàn toàn |
| `tryAcquireShared(int arg)` | Có lấy được quyền chia sẻ ngay không? | Âm: thất bại; `0`: thành công nhưng không còn khả năng cấp chia sẻ tiếp; dương: thành công và có thể còn khả năng đó |
| `tryReleaseShared(int arg)` | Cập nhật việc nhả quyền chia sẻ | `true`: lần nhả có thể cho phép yêu cầu chờ thành công; `false`: không có hiệu ứng đó |
| `isHeldExclusively()` | Luồng hiện tại có giữ quyền độc quyền không? | `true`/`false` theo quy tắc sở hữu của bộ đồng bộ |

Các phương thức trên mặc định ném `UnsupportedOperationException`; chỉ cài đặt các chế độ mà lớp bao thực sự hỗ trợ. Điểm mở rộng phải an toàn khi có cạnh tranh và thường cần ngắn, không chặn luồng. [Hợp đồng các hook AQS](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.html)

Đừng thống nhất mọi kết quả thành quy ước “khác 0 là thành công”. Đặc biệt, `tryAcquireShared` trả `0` vẫn là thành công. Cũng đừng hiểu `false` từ `tryRelease` là “không thay đổi gì”: với khóa tái nhập, giảm số lần giữ từ hai xuống một là một lần nhả có tác dụng, nhưng quyền độc quyền vẫn chưa được nhả hoàn toàn.

## 4. Tham số `arg` do thiết kế của lớp con quy định

AQS truyền đối số đến điểm mở rộng; nó không áp một nghĩa chung như “số luồng cần đánh thức”. Trong khóa đơn ở ví dụ bên dưới, lớp bao luôn truyền `1`. Trong một bộ đồng bộ cho phép lấy nhiều giấy phép, `arg` có thể là số giấy phép yêu cầu. Khi đó, lớp con phải kiểm tra miền giá trị, phép trừ, phép cộng và giới hạn để trạng thái luôn hợp lệ.

Cần nhất quán giữa lớp bao và `Sync`: nếu chỉ hỗ trợ một giấy phép mỗi lần, đừng xuất API nhận mọi `int` rồi âm thầm bỏ qua nó. Các tham số `ignored` trong chương trình minh họa chỉ tồn tại trong lớp trợ giúp riêng; các phương thức bao không nhận số lượng và luôn truyền `1`.

## 5. Viết `tryAcquire` và `tryRelease` ở chế độ độc quyền

Với khóa đơn không tái nhập, đặc tả có thể là:

- `state = 0`: không ai giữ khóa.
- `state = 1`: có đúng một luồng đang giữ khóa.
- Chỉ luồng giữ khóa được nhả khóa.
- Cùng một luồng thử lấy lần hai vẫn thất bại; gọi `lock()` lần hai khi chưa nhả sẽ tự chặn mình.

`tryAcquire` dùng CAS để chiếm chuyển trạng thái `0 → 1`. Hai luồng cùng thấy khóa rảnh không thể cùng thành công ở cùng phép chuyển đó. Sau khi thắng, lớp con ghi nhận luồng chủ sở hữu. Khi thất bại, trả `false` để AQS quyết định đường chờ; không tự ngủ, không tự chỉnh liên kết hàng đợi.

`tryRelease` kiểm tra quyền sở hữu trước. Nhả khóa bằng một luồng không sở hữu là lỗi sử dụng, thường được biểu đạt bằng `IllegalMonitorStateException`. Với khóa đơn này, xóa chủ sở hữu rồi ghi trạng thái `0` và trả `true`: khóa đã rảnh hoàn toàn.

Thứ tự xóa chủ sở hữu **trước** khi công bố khóa rảnh có ý nghĩa. Nếu công bố rảnh trước, một luồng mới có thể lấy khóa và ghi chủ sở hữu mới, sau đó bị lần nhả cũ xóa thông tin sở hữu. Các trường quản lý chủ sở hữu không tự biến thành một khóa; chúng phải phối hợp với quy tắc trạng thái.

### Nếu muốn tái nhập thì phải thiết kế thêm

Giả sử khóa tái nhập dùng số dương để đếm số lần giữ. Khi luồng chủ sở hữu lấy thêm, nó tăng số đếm thay vì cạnh tranh CAS với chính mình. Khi nhả bớt, nó giảm số đếm. Chỉ khi số đếm về `0` mới xóa chủ sở hữu và trả `true` từ `tryRelease`. Phải xử lý cả giới hạn số đếm và việc nhả sai số lần. Chỉ thay `0/1` bằng bộ đếm mà bỏ kiểm tra chủ sở hữu sẽ không tạo ra khóa tái nhập an toàn.

Không thêm tái nhập chỉ để giống một khóa khác. Đó là một phần hợp đồng mà người dùng cần biết trước khi sử dụng.

## 6. Viết biến thể shared: thành công có thể trả về 0

Xét một bộ đồng bộ có tối đa hai giấy phép và mỗi yêu cầu lấy một giấy phép:

```text
state = số giấy phép đang còn

2 → lấy một → 1: thành công, có thể còn yêu cầu khác được cấp
1 → lấy một → 0: thành công, chưa thể cấp thêm
0 → lấy một: thất bại, không được làm state thành âm
```

`tryAcquireShared` có thể trả số giấy phép còn lại sau CAS. Khi còn đúng một giấy phép, phép lấy thành công trả `0`. Nếu lớp bao dùng điều kiện `> 0` thay cho `>= 0`, nó sẽ báo thất bại dù vừa lấy được giấy phép: tài nguyên đã bị trừ mà bên gọi lại tưởng mình không có quyền.

`tryReleaseShared` cộng lại giấy phép bằng CAS. Với thiết kế này, mỗi lần trả hợp lệ có thể giúp một yêu cầu đang chờ đi tiếp nên trả `true`. Khi CAS thất bại, phải đọc lại trạng thái và tính lại; không lặp mãi với một giá trị đã cũ. Giá trị trả về của hook là thông tin phối hợp cho AQS, không phải cam kết số luồng sẽ lập tức được hệ điều hành cho chạy. [API chia sẻ AQS](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.html)

Một trường hợp khác để thấy ý nghĩa `false`: bộ đếm chờ hoàn tất có thể giảm từ `3` xuống `2`, nhưng điều kiện “đếm về 0” vẫn chưa đúng. Trạng thái đã đổi mà chưa cho phép người chờ đi qua; hook nhả chia sẻ có thể trả `false` theo đặc tả đó. Bởi vậy không sao chép máy móc `return true` từ một semaphore sang mọi bộ đồng bộ chia sẻ.

## 7. Chương trình hoàn chỉnh: khóa đơn và hai giấy phép

Lưu mã sau vào `AqsHooksDemo.java`. `Mutex` không tái nhập; `TwoPermits` chỉ cho lấy/trả một giấy phép mỗi lần. Đây là các lớp thực nghiệm, không cài đặt toàn bộ giao diện `Lock`, không cung cấp `Condition`, không cam kết công bằng và không cung cấp hợp đồng tuần tự hóa cho ứng dụng.

```java
import java.util.concurrent.locks.AbstractQueuedSynchronizer;

public class AqsHooksDemo {
    static final class Mutex {
        private static final class Sync extends AbstractQueuedSynchronizer {
            private static final long serialVersionUID = 1L;

            @Override
            protected boolean tryAcquire(int ignored) {
                if (!compareAndSetState(0, 1)) {
                    return false;
                }
                setExclusiveOwnerThread(Thread.currentThread());
                return true;
            }

            @Override
            protected boolean tryRelease(int ignored) {
                if (!isHeldExclusively()) {
                    throw new IllegalMonitorStateException();
                }
                setExclusiveOwnerThread(null);
                setState(0);
                return true;
            }

            @Override
            protected boolean isHeldExclusively() {
                return getState() == 1
                        && getExclusiveOwnerThread() == Thread.currentThread();
            }

            boolean attempt() {
                return tryAcquire(1);
            }
        }

        private final Sync sync = new Sync();

        void lock() { sync.acquire(1); }
        boolean tryLock() { return sync.attempt(); }
        void unlock() { sync.release(1); }
    }

    static final class TwoPermits {
        private static final class Sync extends AbstractQueuedSynchronizer {
            private static final long serialVersionUID = 1L;

            Sync() { setState(2); }

            @Override
            protected int tryAcquireShared(int ignored) {
                for (;;) {
                    int available = getState();
                    if (available == 0) {
                        return -1;
                    }
                    int remaining = available - 1;
                    if (compareAndSetState(available, remaining)) {
                        return remaining;
                    }
                }
            }

            @Override
            protected boolean tryReleaseShared(int ignored) {
                for (;;) {
                    int available = getState();
                    if (available == 2) {
                        throw new IllegalStateException("Too many releases");
                    }
                    if (compareAndSetState(available, available + 1)) {
                        return true;
                    }
                }
            }

            boolean attempt() {
                return tryAcquireShared(1) >= 0;
            }
        }

        private final Sync sync = new Sync();

        void acquire() throws InterruptedException {
            sync.acquireSharedInterruptibly(1);
        }
        boolean tryAcquire() { return sync.attempt(); }
        void release() { sync.releaseShared(1); }
    }

    public static void main(String[] args) throws InterruptedException {
        Mutex mutex = new Mutex();
        mutex.lock();
        try {
            System.out.println("reentry=" + mutex.tryLock());
        } finally {
            mutex.unlock();
        }

        try {
            mutex.unlock();
        } catch (IllegalMonitorStateException expected) {
            System.out.println("invalidUnlock=rejected");
        }

        int[] counter = {0};
        Runnable task = () -> {
            for (int i = 0; i < 500; i++) {
                mutex.lock();
                try {
                    counter[0]++;
                } finally {
                    mutex.unlock();
                }
            }
        };
        Thread first = new Thread(task);
        Thread second = new Thread(task);
        first.start();
        second.start();
        first.join();
        second.join();
        System.out.println("counter=" + counter[0]);

        TwoPermits permits = new TwoPermits();
        permits.acquire();
        permits.acquire();
        System.out.println("third=" + permits.tryAcquire());
        permits.release();
        System.out.println("afterRelease=" + permits.tryAcquire());
        permits.release();
        permits.release();
        try {
            permits.release();
        } catch (IllegalStateException expected) {
            System.out.println("extraRelease=rejected");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac AqsHooksDemo.java
java AqsHooksDemo
```

Stdout:

```text
reentry=false
invalidUnlock=rejected
counter=1000
third=false
afterRelease=true
extraRelease=rejected
```

### Vì sao từng dòng có kết quả đó?

**`reentry=false`**: luồng chính đang giữ khóa, nên CAS `0 → 1` ở lần thử tiếp theo không thể thành công. Dùng `tryLock()` trong phép thử giúp chương trình không tự chặn như gọi thêm `lock()`.

**`invalidUnlock=rejected`**: luồng chính đã nhả trong `finally`; lần nhả tiếp không có quyền sở hữu nên bị từ chối. Việc kiểm tra chủ sở hữu cũng là cơ sở để từ chối luồng khác nhả khóa đang được giữ, dù chương trình này minh họa trường hợp đã không còn chủ sở hữu.

**`counter=1000`**: hai luồng cùng thực hiện 500 lần tăng, và mỗi phép tăng nằm trong cặp lấy/nhả khóa. `counter[0]++` là thao tác đọc–sửa–ghi, được bảo vệ bởi `Mutex`; `join()` bảo đảm luồng chính chỉ đọc kết quả sau khi cả hai đã kết thúc. Không cần dự đoán luồng nào tăng trước. Kết quả này là minh chứng hành vi của ví dụ, không thay thế chứng minh đúng cho mọi cách dùng khóa tùy biến.

**`third=false`**: hai giấy phép đã được lấy; yêu cầu thứ ba thất bại mà không làm trạng thái âm. **`afterRelease=true`**: trả một giấy phép làm trạng thái từ `0` lên `1`; lần thử tiếp lấy được nó và đưa trạng thái về `0`. Hook trả `0` nhưng lớp bao vẫn phải trả `true`.

**`extraRelease=rejected`**: sau khi trả đủ hai giấy phép, lần trả thừa bị chặn bởi giới hạn `2`. Đây là kiểm tra giới hạn toàn cục, không phải theo dõi chủ sở hữu giấy phép. Nếu một luồng trả nhầm hai lần trong lúc một luồng khác vẫn giữ giấy phép, chỉ kiểm tra giới hạn có thể chưa phát hiện ngay lỗi. Người dùng phải giữ đúng cặp lấy/trả; muốn kiểm soát danh tính mỗi lượt cấp cần một thiết kế khác.

### Điểm cấp quyền và vì sao không chỉ dùng setState

Trong `Mutex`, CAS `0 → 1` thành công là điểm chiếm khóa. Trong `TwoPermits`, CAS giảm số giấy phép thành công là điểm cấp một giấy phép. Vòng CAS bảo vệ thao tác tổng hợp đọc–tính–ghi khi có cạnh tranh. Nếu thay nó bằng `setState(getState() - 1)`, hai yêu cầu có thể cùng tính từ một giá trị cũ và làm sai số giấy phép.

`setState(0)` khi nhả `Mutex` có ngữ cảnh khác: chỉ chủ sở hữu hợp lệ thực hiện đường nhả, còn luồng khác chỉ có thể chiếm sau khi trạng thái được công bố rảnh. `setState(2)` trong hàm tạo `TwoPermits.Sync` diễn ra khi khởi tạo, trước khi đối tượng được chia sẻ. Phải hiểu ngữ cảnh đó trước khi chọn giữa ghi trực tiếp và CAS.

## 8. Đường lấy quyền, ngắt và thời hạn thuộc lớp bao

Hook chỉ trả lời liệu có thể lấy ngay. API mà lớp bao chọn sẽ quyết định yêu cầu phải chờ ra sao:

| API lớp bao muốn cung cấp | Cách gọi AQS phù hợp |
| --- | --- |
| Khóa độc quyền chờ không hủy vì ngắt | `acquire(1)` |
| Khóa độc quyền chờ có thể hủy vì ngắt | `acquireInterruptibly(1)` |
| Khóa độc quyền chờ có thời hạn | `tryAcquireNanos(1, timeoutNanos)` |
| Lấy chia sẻ có thể hủy vì ngắt | `acquireSharedInterruptibly(1)` |
| Lấy chia sẻ có thời hạn | `tryAcquireSharedNanos(1, timeoutNanos)` |

Chọn đường có thời hạn không yêu cầu hook tự đo đồng hồ. Chọn đường có thể ngắt không yêu cầu hook tự `sleep` rồi kiểm tra `isInterrupted`. Hãy giữ một quy tắc lấy quyền thống nhất, để AQS xử lý các biến thể chờ của nó. Nếu lớp bao cho phép `InterruptedException` thì truyền ngoại lệ hoặc xử lý theo chính sách rõ ràng; đừng bắt rồi bỏ qua vì điều đó đổi hợp đồng mà bên gọi đang dựa vào.

Trong ví dụ, `TwoPermits.acquire()` chỉ trả về bình thường khi đã lấy thành công. Với mã ứng dụng dùng phương thức có thể ngắt, đặt khối `try/finally` trả giấy phép **sau khi** lấy thành công:

```java
// Đoạn sử dụng, đặt trong phương thức cho phép ném InterruptedException.
permits.acquire();
try {
    // Thực hiện công việc cần một giấy phép.
} finally {
    permits.release();
}
```

Nếu đặt `acquire()` bên trong cùng khối `try` rồi luôn `release()` trong `finally`, một lần bị ngắt trước khi lấy được quyền có thể vẫn trả giấy phép mà nó chưa có. Đó là lỗi ở giao thức sử dụng, không phải lỗi mà hook nhả quyền tự biết hết để sửa.

## 9. isHeldExclusively, Condition và công bằng

`isHeldExclusively()` trả lời quyền độc quyền của **luồng hiện tại**. Kiểm tra `getState() != 0` đơn thuần chỉ nói có ai đó giữ, chưa nói người gọi đang giữ. Với khóa có chủ sở hữu, phải kiểm tra cả chủ sở hữu theo thiết kế.

`ConditionObject` có thêm yêu cầu về việc nhả hoàn toàn và khôi phục trạng thái giữ khóa khi chờ điều kiện. Chỉ tạo nó khi `isHeldExclusively`, `release(savedState)` và đường lấy lại quyền đáp ứng đúng hợp đồng; không thêm vào bộ giấy phép chia sẻ chỉ vì nó là lớp lồng trong AQS. [Hợp đồng ConditionObject](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.ConditionObject.html)

Công bằng cũng không tự sinh ra từ việc đã kế thừa AQS. Có thể dùng `hasQueuedPredecessors()` trong chính sách lấy quyền phù hợp để hạn chế chen hàng, nhưng còn phải xem tái nhập và mọi đường lấy quyền công khai. Chỉ thêm một câu kiểm tra ở một chỗ rồi gọi cả lớp là “khóa công bằng” là chưa đủ. Ví dụ thư viện `ReentrantLock(true)` còn quy định riêng rằng `tryLock()` không thời hạn không tuân theo lựa chọn công bằng. [Công bằng trong ReentrantLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)

## 10. Những lỗi hook dễ gây treo hoặc sai quyền

| Lỗi | Vì sao nguy hiểm? | Hướng sửa |
| --- | --- | --- |
| `tryAcquire` gọi `acquire` của chính nó | Tạo vòng gọi lồng nhau thay vì một lần thử | Kiểm tra/cập nhật trạng thái rồi trả kết quả |
| Hook tự `park`, chờ I/O hoặc lấy khóa chậm khác | Can thiệp đường chờ và làm khó phân tích tiến trình | Giữ hook ngắn, không chặn |
| Lớp bao nhả bằng cách chỉ gọi thẳng `tryRelease` | Bỏ qua phối hợp đánh thức của `release` | Nhả qua API AQS tương ứng |
| Trả `true` khi chưa thực sự chiếm trạng thái | Báo có quyền mà không bảo vệ tài nguyên | Xác định điểm CAS/điểm cấp quyền rõ ràng |
| Trả `false` sau khi đã lấy giấy phép | Bên gọi mất dấu quyền đã cấp | Tuân thủ dấu của kết quả shared |
| Khóa tái nhập trả `true` khi số giữ vẫn dương | Báo nhả hoàn toàn sai thời điểm | Chỉ trả `true` khi thực sự hết quyền giữ |
| Chủ sở hữu bị xóa sau khi công bố rảnh | Có thể xóa nhầm chủ sở hữu mới | Cập nhật theo giao thức nhả nhất quán |
| Không kiểm tra đầu vào hoặc giới hạn bộ đếm | Trạng thái có thể âm/tràn hoặc vượt dung lượng | Kiểm tra trước phép cập nhật phù hợp |

Không gọi `unpark` thủ công trong hook để bù cho giá trị trả về sai. Hãy sửa đặc tả chuyển trạng thái và kết quả trả về; AQS sẽ dùng hợp đồng đó để phối hợp phần chờ.

## 11. Tự kiểm tra kiến thức

1. **Hai giấy phép còn một, yêu cầu lấy một thành công. Hook shared nên trả dấu gì?** Có thể trả `0`, vì lấy thành công nhưng sau đó không còn giấy phép. Lớp bao phải coi `>= 0` là thành công.
2. **Nhả khóa tái nhập từ số giữ 3 xuống 2 trả `false` có nghĩa là lỗi không?** Không. Nó đã nhả một lượt nhưng chưa nhả hoàn toàn quyền độc quyền.
3. **Có cần cài cả exclusive và shared cho mọi lớp Sync không?** Không. Chỉ cài chế độ mà API của bộ đồng bộ hỗ trợ và cần dùng.
4. **Lớp bao dùng tryAcquire trực tiếp có luôn sai không?** Không. Một đường thử ngay, không chờ có thể gọi điểm thử thông qua phương thức trợ giúp như ví dụ. Nhưng đó không thay thế cho `acquire` khi cần chờ, và nhả quyền vẫn cần qua `release` để phối hợp người chờ.
5. **Thấy state bằng 1 có đủ để cho phép unlock không?** Không. Trong khóa đơn có chủ sở hữu, còn phải xác minh luồng hiện tại là người giữ khóa.
6. **Muốn thêm API lấy ba giấy phép vào TwoPermits thì chỉ truyền arg = 3 được không?** Không. Ví dụ bỏ qua arg và dung lượng chỉ là hai; cần thiết kế lại miền đầu vào, phép chuyển và cách trả giấy phép trước khi mở rộng API.
