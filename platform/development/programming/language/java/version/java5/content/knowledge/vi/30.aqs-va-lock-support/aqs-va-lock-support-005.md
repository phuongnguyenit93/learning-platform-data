# Quản lý chủ sở hữu khi xây dựng bộ đồng bộ độc quyền

## 1. Khóa đang bận chưa trả lời được ai có quyền nhả khóa

Giả sử một bộ đồng bộ chỉ dùng trạng thái `0` để biểu diễn “rảnh” và `1` để biểu diễn “đang được giữ”. Hai luồng cùng thử chuyển `0 → 1` bằng phép so sánh và cập nhật nguyên tử (CAS) thì chỉ một luồng thắng. Cách đó có thể ngăn hai luồng cùng đi vào vùng tới hạn.

Nhưng nếu bất kỳ luồng nào cũng được đặt trạng thái về `0`, một luồng chưa từng nhận khóa có thể nhả khóa thay luồng đang sử dụng tài nguyên. Tính độc quyền bị phá vỡ ngay khi một luồng thứ ba nhận khóa và đi vào cùng vùng dữ liệu.

**Chủ sở hữu (owner)** là luồng đã nhận quyền độc quyền thành công và chưa nhả quyền đó hoàn toàn. Quản lý chủ sở hữu nhằm trả lời:

- Luồng hiện tại có được phép `unlock()` không?
- Luồng hiện tại có đang giữ khóa để gọi `Condition.await()` hoặc `signal()` không?
- Nếu khóa cho phép nhận lại nhiều lần, ai được tăng số lần giữ?
- Công cụ chẩn đoán có thể chỉ ra luồng nào đang giữ bộ đồng bộ không?

Ở đây, “sở hữu” là một phần của giao thức đồng bộ trong bộ nhớ. Nó không phải quyền sở hữu đối tượng Java nói chung, không phải quyền của người dùng và không phải việc gán một tên luồng vào biến để theo dõi.

Bài học dùng mô hình AQS hiện hành trên Java 17 trở lên. Với mã ứng dụng thông thường, ưu tiên `ReentrantLock` hoặc bộ đồng bộ có sẵn; ví dụ tự xây dưới đây giúp hiểu và kiểm chứng các bất biến khi thật sự cần xây một bộ đồng bộ riêng.

## 2. Ba thông tin có vai trò khác nhau

### 2.1. Trạng thái quyết định quyền nhận khóa

`AbstractQueuedSynchronizer` (AQS) cung cấp một trạng thái số nguyên, truy cập qua `getState()`, `setState(...)` và `compareAndSetState(...)`. Lớp con định nghĩa trạng thái đó có nghĩa gì; AQS cung cấp cơ chế xếp hàng, chờ và thử lại dựa trên các phương thức mà lớp con triển khai.

Với mutex không cho nhận lại của bài này:

| Trạng thái | Ý nghĩa |
| --- | --- |
| `state == 0` | Có thể tranh quyền nhận khóa |
| `state == 1` | Quyền độc quyền đã được một luồng chiếm |
| Giá trị khác | Không thuộc giao thức của mutex này |

Chuyển `0 → 1` phải là thao tác nguyên tử. Đoạn `if (getState() == 0) setState(1)` không đủ: hai luồng có thể cùng đọc `0` rồi cùng cho rằng mình nhận khóa thành công.

### 2.2. Chủ sở hữu quyết định ai được thao tác đặc quyền

AQS kế thừa khả năng lưu chủ sở hữu từ `AbstractOwnableSynchronizer`, thông qua:

```java
// Các phương thức protected mà lớp con có thể dùng.
setExclusiveOwnerThread(Thread.currentThread());
Thread owner = getExclusiveOwnerThread();
setExclusiveOwnerThread(null);
```

Các phương thức này chỉ lưu và đọc thông tin luồng sở hữu; lớp nền không tự xác thực người gọi, không tự trao quyền và không tự chèn truy cập `volatile` cho trường chủ sở hữu. Chính lớp con phải giữ thông tin đó phù hợp với giao thức trạng thái. [Tài liệu AbstractOwnableSynchronizer](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractOwnableSynchronizer.html)

Đặt owner mà không chiếm trạng thái nguyên tử không tạo ra một khóa. Ngược lại, chỉ chiếm trạng thái mà không kiểm tra owner khi nhả cũng chưa tạo được khóa có hợp đồng “chỉ người giữ mới được nhả”.

### 2.3. Hàng đợi chỉ ghi nhận người đang chờ

Luồng đã vào hàng đợi AQS chưa phải chủ sở hữu. Luồng vừa được đánh thức cũng chưa phải chủ sở hữu: nó vẫn phải giành quyền qua `tryAcquire`.

Tương tự, tham số `blocker` của `LockSupport.park(blocker)` phục vụ chẩn đoán lý do chờ, không trao quyền nhận hay nhả khóa. `unpark(thread)` chỉ hỗ trợ cho luồng đó tiếp tục kiểm tra điều kiện; nó không tương đương `setExclusiveOwnerThread(thread)`. [Tài liệu LockSupport](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/LockSupport.html)

Nhầm ba vai trò này dễ dẫn đến lỗi “đã đánh thức B thì B chắc chắn là người giữ”, trong khi A hoặc một luồng mới vẫn có thể thắng lần tranh quyền tiếp theo.

## 3. Định nghĩa bất biến trước khi viết tryAcquire và tryRelease

Với mutex không cho nhận lại, hợp đồng là:

1. Chỉ luồng thắng CAS từ `0` sang `1` mới được công bố mình là owner.
2. `lock()` chỉ trả về sau khi luồng nhận khóa đã thiết lập owner.
3. Luồng chưa sở hữu không được sửa trạng thái nhả hoặc xóa owner.
4. Owner phải được xóa trước khi công bố trạng thái rảnh.
5. Sau khi nhả hoàn toàn, luồng cũ không được tiếp tục sửa dữ liệu được khóa bảo vệ.
6. Một luồng đang giữ khóa không nhận lại khóa lần nữa: `tryLock()` trả `false`; gọi `lock()` lồng nhau sẽ tự chờ nếu không có đường ngắt khác.

Đây là hợp đồng riêng của mutex không cho nhận lại. Đừng áp dụng mục 6 cho `ReentrantLock`, vốn có ngữ nghĩa khác.

Cũng không đặt bất biến quá mạnh rằng “tại mọi thời điểm, mọi luồng đọc đều thấy cặp `state` và `owner` nhất quán như một ảnh chụp nguyên tử”. Hai trường không được cập nhật cùng một thao tác. Có những khoảng chuyển tiếp hợp lệ, miễn là không có luồng khác được trao quyền trái phép và các phương thức công khai chỉ trả về ở ranh giới phù hợp.

## 4. Nhận quyền: thắng CAS trước, công bố owner sau

Trình tự đúng cho khóa không cho nhận lại:

```java
// Đoạn minh họa bên trong lớp con AQS.
if (compareAndSetState(0, 1)) {
    setExclusiveOwnerThread(Thread.currentThread());
    return true;
}
return false;
```

Xét hai luồng A và B:

| Bước | Luồng A | Luồng B |
| --- | --- | --- |
| 1 | CAS `0 → 1` thành công | Chưa nhận khóa |
| 2 | Chưa kịp ghi owner | CAS `0 → 1` thất bại vì state đã là 1 |
| 3 | Ghi owner=A | Phải chờ hoặc trả thất bại |
| 4 | Trả thành công về nơi gọi | Chưa có quyền vào vùng tới hạn |

Khoảng thời gian `state == 1` mà owner chưa được thiết lập không cho B quyền nhận khóa. Trạng thái nguyên tử đã chặn B.

Trình tự sai là ghi owner trước khi CAS. Nếu A và B cùng ghi owner rồi chỉ A thắng CAS, owner cuối cùng vẫn có thể là B. A đang giữ quyền thật nhưng bị từ chối khi nhả, còn B có thể được kiểm tra nhầm là người giữ.

Không dùng owner làm cờ “đang rảnh” thay cho CAS. Đọc owner thấy `null` rồi ghi mình vào owner là một chuỗi không nguyên tử và cũng không có bảo đảm đồng bộ của một khóa.

## 5. Nhả quyền: xác thực trước, xóa owner trước khi công bố rảnh

Trình tự của mutex này:

```java
// Đoạn minh họa bên trong lớp con AQS.
if (!isHeldExclusively()) {
    throw new IllegalMonitorStateException("current thread does not own lock");
}
setExclusiveOwnerThread(null);
setState(0);
return true;
```

Ba hành động có ba mục đích:

- Kiểm tra owner bảo vệ quyền nhả: luồng sai phải bị từ chối trước khi sửa bất kỳ dữ liệu đồng bộ nào.
- Xóa owner kết thúc thông tin sở hữu của luồng cũ.
- Ghi `state = 0` công bố khóa đã có thể nhận lại.

### 5.1. Vì sao không đặt state về 0 trước?

Giả sử A nhả theo thứ tự sai:

| Bước | Hành động | Hậu quả |
| --- | --- | --- |
| 1 | A đặt `state = 0` | Khóa đã có thể được nhận |
| 2 | B CAS `0 → 1` thành công | B là người giữ mới |
| 3 | B đặt owner=B | Thông tin B đang đúng |
| 4 | A đặt owner=`null` | A xóa mất thông tin sở hữu của B |

B vẫn đang sử dụng vùng tới hạn nhưng kiểm tra owner không còn nhận ra B. Khóa có thể không nhả được, hoặc các thao tác condition bị từ chối sai.

Với trình tự xóa owner trước rồi mới ghi state về 0, B chưa thể thắng CAS trong lúc A đang xóa thông tin cũ. Khi B nhận được khóa, A đã hoàn tất mọi ghi liên quan đến owner của lượt giữ trước.

### 5.2. Giá trị trả về của tryRelease không chỉ để báo “hàm chạy xong”

Ở chế độ độc quyền, `tryRelease` trả `true` khi quyền độc quyền đã được nhả hoàn toàn, để AQS thực hiện phần đánh thức phù hợp. Với khóa có đếm số lần giữ, nhả một tầng nhưng còn tầng khác phải trả `false`.

Các phương thức `tryAcquire`, `tryRelease` nên ngắn, an toàn luồng và không tự chặn. Không gọi mạng, chờ latch hoặc tự `park` trong chúng. Cơ chế chờ thuộc phần AQS điều phối. [Tài liệu AQS](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.html)

## 6. isHeldExclusively phải nói về luồng hiện tại

Một triển khai phù hợp cho mutex này:

```java
@Override
protected boolean isHeldExclusively() {
    return getState() == 1
            && getExclusiveOwnerThread() == Thread.currentThread();
}
```

Chỉ kiểm tra `getState() == 1` trả lời “khóa đang bị giữ”, không trả lời “chính tôi đang giữ khóa”. Nếu dùng kiểm tra đó để cho phép `unlock()` hoặc `signal()`, một luồng lạ có thể được cấp quyền.

So sánh đối tượng `Thread` bằng `==`, không so sánh tên. Hai luồng có thể cùng tên; tên cũng có thể đổi trong quá trình chạy. Quyền thuộc về đối tượng luồng cụ thể đã nhận khóa.

Một phương thức công khai tên `isHeldByCurrentThread()` có thể ủy quyền cho kiểm tra trên. Nó hữu ích để chẩn đoán và kiểm tra tiền điều kiện. Nhưng không tạo lối dùng “nếu ai đó đang giữ thì tôi tự nhả”: kết quả quan sát không phải giấy phép chuyển quyền.

Các phương thức báo “đang khóa hay không”, độ dài hàng đợi hoặc tên owner thường chỉ là thông tin chẩn đoán. Chúng không thay thế thao tác nhận khóa thật, và không hứa cung cấp một ảnh chụp nhất quán của toàn bộ hệ thống đang thay đổi.

## 7. Ví dụ hoàn chỉnh: mutex kiểm tra owner và hỗ trợ Condition

Tạo tệp `OwnerLockDemo.java`. `OwnedMutex` có các quy tắc:

- Không cho nhận lại, không bảo đảm công bằng.
- `unlock()` sai luồng ném `IllegalMonitorStateException`.
- `lockInterruptibly()` và `tryLock(timeout, unit)` dùng cơ chế ngắt/thời hạn của AQS.
- Condition gắn với chính mutex; nơi gọi phải đang giữ mutex khi chờ hoặc báo hiệu.
- Lớp bao không triển khai `Serializable`; ví dụ không đặt ra hợp đồng tuần tự hóa.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.AbstractQueuedSynchronizer;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.Lock;

public class OwnerLockDemo {
    static final class OwnedMutex implements Lock {
        private final Sync sync = new Sync();

        private static final class Sync extends AbstractQueuedSynchronizer {
            private static final long serialVersionUID = 1L;

            @Override
            protected boolean tryAcquire(int acquires) {
                if (acquires != 1) {
                    throw new IllegalArgumentException("acquires must be 1");
                }
                if (compareAndSetState(0, 1)) {
                    setExclusiveOwnerThread(Thread.currentThread());
                    return true;
                }
                return false;
            }

            @Override
            protected boolean tryRelease(int releases) {
                if (releases != 1) {
                    throw new IllegalArgumentException("releases must be 1");
                }
                if (!isHeldExclusively()) {
                    throw new IllegalMonitorStateException(
                            "current thread does not own lock");
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

            Condition condition() {
                return new ConditionObject();
            }
        }

        @Override
        public void lock() {
            sync.acquire(1);
        }

        @Override
        public void lockInterruptibly() throws InterruptedException {
            sync.acquireInterruptibly(1);
        }

        @Override
        public boolean tryLock() {
            return sync.tryAcquire(1);
        }

        @Override
        public boolean tryLock(long time, TimeUnit unit)
                throws InterruptedException {
            return sync.tryAcquireNanos(1, unit.toNanos(time));
        }

        @Override
        public void unlock() {
            sync.release(1);
        }

        @Override
        public Condition newCondition() {
            return sync.condition();
        }

        public boolean isHeldByCurrentThread() {
            return sync.isHeldExclusively();
        }
    }

    public static void main(String[] args) throws Exception {
        OwnedMutex lock = new OwnedMutex();
        ExecutorService pool = Executors.newFixedThreadPool(4);
        try {
            lock.lock();
            try {
                System.out.println("heldByMain="
                        + lock.isHeldByCurrentThread());
                System.out.println("reentrantTry=" + lock.tryLock());
                Future<String> foreignUnlock = pool.submit(() -> {
                    try {
                        lock.unlock();
                        return "WRONG";
                    } catch (IllegalMonitorStateException expected) {
                        return "REJECTED";
                    }
                });
                System.out.println("foreignUnlock="
                        + foreignUnlock.get(5, TimeUnit.SECONDS));
            } finally {
                lock.unlock();
            }

            boolean acquired = lock.tryLock();
            try {
                System.out.println("availableAfterUnlock=" + acquired);
            } finally {
                if (acquired) {
                    lock.unlock();
                }
            }

            Condition changed = lock.newCondition();
            CountDownLatch aboutToWait = new CountDownLatch(1);
            boolean[] ready = {false};
            Future<Boolean> waiter = pool.submit(() -> {
                lock.lockInterruptibly();
                try {
                    while (!ready[0]) {
                        aboutToWait.countDown();
                        changed.await();
                    }
                    return lock.isHeldByCurrentThread();
                } finally {
                    lock.unlock();
                }
            });

            if (!aboutToWait.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("waiter did not start");
            }
            lock.lock();
            try {
                ready[0] = true;
                changed.signal();
            } finally {
                lock.unlock();
            }
            System.out.println("conditionOwnerRestored="
                    + waiter.get(5, TimeUnit.SECONDS));

            try {
                changed.signal();
                System.out.println("foreignSignal=WRONG");
            } catch (IllegalMonitorStateException expected) {
                System.out.println("foreignSignal=REJECTED");
            }

            int[] counter = {0};
            List<Future<?>> workers = new ArrayList<>();
            for (int worker = 0; worker < 4; worker++) {
                workers.add(pool.submit(() -> {
                    for (int i = 0; i < 1_000; i++) {
                        lock.lock();
                        try {
                            counter[0]++;
                        } finally {
                            lock.unlock();
                        }
                    }
                }));
            }
            for (Future<?> worker : workers) {
                worker.get(5, TimeUnit.SECONDS);
            }
            System.out.println("counter=" + counter[0]);

            lock.lock();
            try {
                Future<Boolean> contender = pool.submit(() -> {
                    boolean success = lock.tryLock(50, TimeUnit.MILLISECONDS);
                    if (success) {
                        lock.unlock();
                    }
                    return success;
                });
                System.out.println("timedContender="
                        + contender.get(5, TimeUnit.SECONDS));

                Future<Boolean> interrupted = pool.submit(() -> {
                    Thread.currentThread().interrupt();
                    try {
                        lock.lockInterruptibly();
                        try {
                            return false;
                        } finally {
                            lock.unlock();
                        }
                    } catch (InterruptedException expected) {
                        Thread.currentThread().interrupt();
                        return true;
                    }
                });
                System.out.println("interruptBeforeAcquire="
                        + interrupted.get(5, TimeUnit.SECONDS));
            } finally {
                lock.unlock();
            }
        } finally {
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                System.err.println("POOL_NOT_TERMINATED");
            }
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac -encoding UTF-8 OwnerLockDemo.java
java OwnerLockDemo
```

Stdout trong điều kiện chạy thông thường:

```text
heldByMain=true
reentrantTry=false
foreignUnlock=REJECTED
availableAfterUnlock=true
conditionOwnerRestored=true
foreignSignal=REJECTED
counter=4000
timedContender=false
interruptBeforeAcquire=true
```

Chương trình chỉ in từ luồng `main` sau khi lấy kết quả nên thứ tự stdout không phụ thuộc thứ tự các tác vụ tự in. Các thời hạn 5 giây là giới hạn chống chờ vô hạn trong minh họa; một môi trường bị treo lâu vẫn có thể làm ví dụ kết thúc bằng ngoại lệ hết thời gian.

### 7.1. Mỗi kết quả chứng minh điều gì?

- `foreignUnlock=REJECTED`: một luồng khác không được nhả khóa của main, và khóa vẫn thuộc main để main nhả ở `finally`.
- `availableAfterUnlock=true`: lượt nhả hợp lệ đã công bố trạng thái rảnh cho lượt nhận tiếp theo.
- `conditionOwnerRestored=true`: sau khi chờ condition, tác vụ đã nhận lại khóa và thiết lập lại owner trước khi đi tiếp.
- `foreignSignal=REJECTED`: trạng thái khóa không cấp quyền báo hiệu cho luồng hiện tại khi nó không còn giữ khóa.
- `counter=4000`: trong lần chạy, bốn tác vụ cùng dùng khóa đã bảo vệ được phép tăng không nguyên tử.
- `timedContender=false`: một luồng khác không nhận được khóa trong khi main vẫn giữ.
- `interruptBeforeAcquire=true`: phương thức nhận có khả năng ngắt phản hồi trạng thái ngắt ngay từ đầu.

Bốn nghìn lần tăng đúng không phải chứng minh toán học rằng bộ đồng bộ không có lỗi. Chứng minh thiết kế phải dựa trên bất biến, thứ tự thao tác và quy tắc bộ nhớ; chạy thử bổ sung bằng chứng cho các đường cụ thể.

### 7.2. Vì sao không dùng sleep để kiểm tra Condition?

Tác vụ chờ hạ latch khi vẫn đang giữ mutex rồi gọi `await()`. Main chỉ bắt đầu tranh mutex sau khi thấy latch đã hạ. Vì main phải lấy được mutex mới đặt `ready = true` và `signal()`, nó không thể báo hiệu trong một đoạn kiểm tra điều kiện chưa được bảo vệ bởi khóa.

Nếu việc chờ thức dậy giả rồi kiểm tra lại `ready`, vòng `while` vẫn đúng. Latch giúp sắp xếp các mốc kiểm chứng; mutex và condition mới là giao thức bảo vệ dữ liệu và chờ điều kiện.

## 8. Condition làm rõ yêu cầu quản lý owner

Một condition không chỉ “cho luồng ngủ rồi đánh thức”. Với `AQS.ConditionObject`, đường chờ liên quan trực tiếp tới trạng thái khóa:

1. Ghi nhớ trạng thái đang giữ.
2. Nhả hoàn toàn quyền độc quyền.
3. Chờ điều kiện hoặc bị ngắt/hết thời gian.
4. Tranh và nhận lại quyền độc quyền bằng trạng thái đã lưu.
5. Chỉ sau đó tiếp tục đoạn mã của nơi gọi theo ngữ nghĩa của phương thức chờ.

Do đó, `tryRelease` phải thật sự nhả được toàn bộ trạng thái đã lưu, `tryAcquire` phải khôi phục được nó, còn `isHeldExclusively` phải nhận diện đúng luồng đang giữ. Không đáp ứng các yêu cầu đó thì không nên cung cấp `ConditionObject` từ bộ đồng bộ. [Tài liệu ConditionObject](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/AbstractQueuedSynchronizer.ConditionObject.html)

Trong ví dụ, trạng thái giữ luôn là `1`, nên nhả rồi nhận lại bằng `1` khớp với giao thức mutex.

`signal()` không nhường khóa ngay cho luồng chờ. Luồng báo hiệu vẫn giữ khóa cho đến khi nhả; luồng được báo hiệu phải nhận lại khóa trước khi kiểm tra điều kiện. Điều kiện dùng chung phải được kiểm tra trong vòng `while`, vì có thể thức dậy giả hoặc một luồng khác đã làm điều kiện không còn đúng. [Tài liệu Condition](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/Condition.html)

Không gọi `wait()` hoặc `notify()` trên đối tượng `Condition` rồi cho rằng chúng dùng cùng giao thức với `await()` và `signal()`. Monitor nội tại của đối tượng và mutex AQS là hai cơ chế khác nhau.

## 9. Nếu cần khóa cho phép nhận lại, owner trở thành nhánh điều khiển

Khóa cho phép nhận lại (reentrant) cho cùng một luồng nhận khóa nhiều lần. Trạng thái thường được dùng làm số lần giữ:

| Tình huống | Xử lý khái niệm |
| --- | --- |
| `state == 0` | Tranh nhận; thành công thì đặt owner và số lần giữ ban đầu |
| `state > 0`, owner là luồng hiện tại | Tăng số lần giữ, có kiểm tra tràn |
| `state > 0`, owner là luồng khác | Không được nhận |
| Owner nhả một phần | Giảm số lần giữ; giữ owner; chưa đánh thức người chờ để nhận độc quyền |
| Owner nhả hết | Xóa owner, công bố state=0, trả trạng thái nhả hoàn toàn |

Hai lần `lock()` thành công cần hai lần `unlock()` tương ứng. Nhả một tầng không có nghĩa là người khác được vào.

Với condition, cần khôi phục toàn bộ số lần giữ sau khi chờ, không chỉ nhận lại một lần. Nếu cải biến ví dụ thành reentrant nhưng vẫn bắt buộc `acquires == 1`, thao tác khôi phục trạng thái lớn hơn 1 của condition sẽ không còn phù hợp.

`ReentrantLock` có sẵn ngữ nghĩa này cùng kiểm tra chủ sở hữu và số lần giữ. Dùng nó khi nhu cầu là một khóa độc quyền tiêu chuẩn, thay vì sao chép một phần cơ chế rồi bỏ sót tràn số, condition hoặc đường hủy chờ. [Tài liệu ReentrantLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html)

Phần này mô tả cách thay đổi hợp đồng; nó không biến mutex không cho nhận lại trong ví dụ thành reentrant. Không thử gọi `lock()` lồng nhau lên mutex đó để kiểm tra: chính luồng giữ sẽ chờ quyền mà nó chưa nhả.

## 10. Tính nhìn thấy dữ liệu đến từ giao thức đồng bộ

Giả sử A sửa một cấu trúc dữ liệu trong vùng tới hạn rồi nhả khóa; B nhận cùng khóa và đọc cấu trúc đó. Khóa phải cung cấp hiệu ứng bộ nhớ tương ứng với thao tác nhận/nhả theo hợp đồng `Lock`. Các truy cập dữ liệu được bảo vệ phải cùng tuân theo giao thức khóa. [Tài liệu Lock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/Lock.html)

Trong mutex AQS:

- Ghi dữ liệu trong vùng tới hạn xảy ra trước thao tác nhả trong thứ tự của luồng A.
- Việc công bố state về trạng thái rảnh và lần nhận nguyên tử tiếp theo tạo nền tảng đồng bộ giữa các lượt giữ.
- Thiết lập owner giúp kiểm tra quyền; riêng thao tác thiết lập owner không phải cơ chế công bố dữ liệu nghiệp vụ.

Một biến owner không có đồng bộ không tự làm các trường dữ liệu khác trở nên an toàn. Cũng không thể đọc dữ liệu ngoài khóa rồi dùng kết quả `isHeldByCurrentThread()` để chữa lại một truy cập sai giao thức.

Trong chương trình, `counter[0]` không phải biến nguyên tử. Mỗi lần tăng nằm trong vùng khóa. Main chỉ đọc sau khi nhận kết quả của mọi `Future`; không đọc trong khi các tác vụ đang thay đổi dữ liệu.

Quy tắc quan hệ “xảy ra trước” (happens-before) giúp giải thích vì sao dữ liệu được công bố giữa các luồng, thay vì dựa vào giả định rằng “chạy trên cùng máy thì sớm muộn sẽ nhìn thấy”. [Java Language Specification, mục 17.4.5](https://docs.oracle.com/javase/specs/jls/se25/html/jls-17.html#jls-17.4.5)

## 11. Những lỗi triển khai và sử dụng dễ gặp

| Lỗi | Vì sao sai? | Cách xử lý |
| --- | --- | --- |
| Ghi owner trước CAS | Luồng thua có thể ghi đè owner của luồng thắng | Chỉ ghi sau khi nhận quyền thành công |
| `unlock()` chỉ kiểm tra state khác 0 | Luồng không sở hữu cũng được nhả | Kiểm tra đúng đối tượng Thread |
| Đặt state=0 rồi mới xóa owner | Luồng cũ có thể xóa owner của lượt nhận mới | Xóa owner trước khi công bố rảnh |
| Xóa owner khi nhả một tầng của khóa reentrant | Luồng vẫn còn giữ nhưng mất danh tính | Chỉ xóa khi số lần giữ về 0 |
| `isHeldExclusively()` kiểm tra “có ai đang giữ” | Condition cấp quyền sai cho người gọi | Kiểm tra “luồng hiện tại đang giữ” |
| Gọi `unlock()` trong finally dù nhận thất bại | Tạo ngoại lệ mới hoặc nhả trái phép | Chỉ lập vùng finally nhả sau khi nhận thành công |
| Tự `park` trong tryAcquire | Trộn cơ chế chờ, hủy và xếp hàng | Để AQS điều phối việc chờ |
| Cho rằng hàng đợi FIFO tự tạo công bằng | Luồng mới có thể tranh trước người đang chờ | Định nghĩa rõ chính sách; không công bố công bằng khi chưa triển khai |
| Dùng cùng mutex nhưng truy cập dữ liệu ngoài khóa | Tính độc quyền của khóa không bao trùm truy cập đó | Thống nhất giao thức cho mọi đường đọc/ghi |

Mẫu sử dụng cơ bản:

```java
// Đoạn minh họa.
lock.lock();
try {
    updateProtectedData();
} finally {
    lock.unlock();
}
```

Với `tryLock()`, chỉ nhả nếu nhận thành công:

```java
// Đoạn minh họa.
if (lock.tryLock()) {
    try {
        updateProtectedData();
    } finally {
        lock.unlock();
    }
} else {
    handleBusyResource();
}
```

Một luồng khác không nên “cứu” khóa bằng cách gọi `unlock()` khi owner bị treo. Điều đó có thể cho hai luồng đồng thời sửa dữ liệu nếu owner chạy tiếp. Thiết kế phục hồi phải xử lý vòng đời tác vụ và trạng thái dữ liệu ở cấp cao hơn, thay vì phá bỏ quyền sở hữu bên trong khóa.

## 12. Giới hạn cần công bố trước khi sử dụng thực tế

Mutex minh họa không có chính sách công bằng. Nó không phát hiện mọi dạng deadlock, không bảo đảm thời gian chờ tối đa cho `lock()` và không khôi phục trạng thái ứng dụng nếu luồng chết giữa lúc sửa dữ liệu.

Nó cũng không có hợp đồng chuyển owner giữa các luồng. Nếu nhu cầu là “một bên nhận giấy phép, bên khác trả giấy phép”, có thể cần bộ đồng bộ với hợp đồng khác, chẳng hạn semaphore, thay vì buộc một mutex kiểm tra owner chấp nhận nhả sai luồng.

Nếu thêm tuần tự hóa, cần thiết kế riêng trạng thái sau khi đọc lại. Không lưu một khóa đang giữ rồi giả định có thể khôi phục cùng quyền sở hữu của một luồng sống. Một bộ đồng bộ được đọc lại với state khác 0 nhưng owner không hợp lệ có thể bị kẹt ngay từ đầu.

Thông tin owner hữu ích cho chẩn đoán, nhưng không thay thế bằng chứng về khả năng tiến triển và tính đúng. Một ảnh thread dump chỉ là một quan sát tại thời điểm cụ thể; muốn đánh giá deadlock cần xem cả chuỗi phụ thuộc và trạng thái thực tế.

## 13. Bài tập kiểm chứng

1. Giải thích bằng một lịch xen kẽ hai luồng vì sao thứ tự `setState(0)` rồi `setExclusiveOwnerThread(null)` sai. Chỉ ra owner của B bị xóa ở đâu.
2. Viết ca kiểm tra một luồng không sở hữu gọi `unlock()` khi khóa đang rảnh. Kết quả phải là ngoại lệ và khóa vẫn nhận được sau đó.
3. Thử `signal()` từ một luồng khác trong khi main đang giữ khóa. Ca này phát hiện được triển khai `isHeldExclusively()` chỉ kiểm tra state.
4. Dùng latch để bảo đảm một tác vụ đang đợi nhận khóa, rồi ngắt nó khi gọi `lockInterruptibly()`. Xác minh tác vụ thoát và owner hiện tại vẫn nhả bình thường.
5. Mô tả thay đổi cần thiết để hỗ trợ số lần giữ trong khóa reentrant: đường nhận lại, tràn số, nhả một phần, nhả hoàn toàn và condition khôi phục nhiều tầng.
6. Đánh giá việc công khai `getOwner()` như một API chẩn đoán: thông tin nào có thể nhất thời không khớp, và vì sao nơi gọi không được dùng nó để quyết định tự nhả khóa?

Khi đọc hoặc xây bộ đồng bộ độc quyền, hãy kiểm tra lần lượt: thao tác nào giành quyền thật, owner được ghi sau thao tác đó ra sao, người nhả được xác thực ở đâu và thông tin cũ được xóa trước khi lượt nhận mới có thể bắt đầu hay chưa.
