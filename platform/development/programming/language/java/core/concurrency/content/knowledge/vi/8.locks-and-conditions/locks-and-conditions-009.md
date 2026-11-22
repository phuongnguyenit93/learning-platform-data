# ReentrantReadWriteLock: nâng/hạ cấp khóa và giới hạn trong Java

Trong một hệ thống nhiều thread, nhiều thao tác chỉ **đọc** cùng một trạng thái, còn thao tác **ghi** cần độc quyền để bảo vệ bất biến. `ReentrantReadWriteLock` cung cấp một cặp khóa liên kết với nhau: `readLock()` để nhiều reader cùng giữ khi không có writer đang nắm khóa, và `writeLock()` để writer có quyền độc quyền. Tuy nhiên, cách chuyển từ đọc sang ghi và từ ghi sang đọc **không đối xứng**: Java cho phép **hạ cấp write → read**, nhưng **không hỗ trợ nâng cấp read → write** khi vẫn giữ read lock.

Bài này thuộc mục **Locks & Conditions**, phạm vi **Java concurrency nói chung**, áp dụng với **Java 17+** và API chuẩn trong `java.util.concurrent.locks`. Không dùng cơ chế riêng của Spring.

Sau bài học, bạn sẽ:
- Biết khi nào dùng read lock, write lock, và tại sao vẫn cần một bất biến cùng giao thức khóa.
- Hiểu ý nghĩa của **reentrancy**, read/write ownership và số lần khóa phải nhả.
- Chứng minh vì sao cố nâng read → write có thể tự chặn vĩnh viễn; biết mẫu **nhả read → lấy write → kiểm tra lại điều kiện**.
- Thực hiện **downgrade** bằng đúng thứ tự **write.lock → read.lock → write.unlock**, rồi đọc tiếp và nhả read lock.
- Nắm giới hạn: fairness, `tryLock`, conditions, interrupt, đo hiệu năng, tránh starvation/deadlock và cách kiểm tra mã.

## 1. ReadWriteLock và hai kiểu quyền truy cập

`java.util.concurrent.locks.ReadWriteLock` là interface có hai phương thức:

~~~java
Lock readLock();
Lock writeLock();
~~~

`ReentrantReadWriteLock` là một implementation có tính **reentrant** và hỗ trợ chính sách **nonfair** (mặc định) hoặc **fair** (được chỉ định qua constructor). Cả hai lock thuộc **cùng một cấu trúc** và điều phối quyền đọc/ghi trên **cùng trạng thái được bảo vệ**.

| Tình trạng hiện tại | Xin read lock | Xin write lock |
| --- | --- | --- |
| Không ai giữ lock | Có thể nhận, tùy chính sách fairness/hàng đợi | Có thể nhận, tùy chính sách fairness/hàng đợi |
| Một hoặc nhiều reader đang giữ | Reader khác có thể cùng đọc nếu chính sách cho phép | Writer khác phải chờ reader nhả hết |
| Một writer đang giữ | Reader khác phải chờ | Writer khác phải chờ |
| **Chính thread** đang giữ write lock | Có thể tái nhập write và lấy thêm read lock | Có thể tái nhập write lock |
| **Chính thread** chỉ đang giữ read lock | Có thể tái nhập read lock | **Không nâng cấp trực tiếp lên write lock** |

Các ô “có thể” phải xét fairness, việc một writer đang chờ và trạng thái interrupt; read lock không phải lệnh bảo đảm reader luôn vào ngay khi có reader khác.

Hai điều cốt lõi:

1. **Read-side concurrency:** nhiều reader có thể cùng vào đoạn chỉ đọc, khi không có writer khác nắm write lock.
2. **Write-side exclusion:** writer giữ write lock loại trừ những reader/writer khác khỏi phần trạng thái được bảo vệ, nhưng chỉ khi **mọi đường truy cập** đều tuân thủ cùng cặp lock.

Sự tách biệt read/write là một quyết định điều phối quyền. Nó **không tự tạo bất biến**, không biến dữ liệu mutable thành immutable, và không bảo vệ những thao tác đọc/ghi thực hiện ngoài khóa.

### 1.1. Memory visibility

Theo hợp đồng `ReadWriteLock`, các hiệu ứng đồng bộ bộ nhớ của write lock áp dụng với read lock tương ứng: reader lấy thành công read lock phải thấy những cập nhật đã được công bố qua lần nhả write lock trước đó theo giao thức khóa. Vì vậy có thể giữ các field được bảo vệ là kiểu bình thường thay vì `volatile` khi **mọi** thao tác phù hợp đều dùng đúng lock.

Tuy nhiên, memory visibility **không thay thế mutual exclusion**: nếu cần thao tác đọc–kiểm tra–cập nhật là một đơn vị, phải lấy write lock cho toàn bộ hành động.

## 2. Ví dụ đọc song song, ghi độc quyền

Trên Java 17, dùng `java.util.concurrent.locks.ReentrantReadWriteLock` với hai handle:

~~~java
private final ReentrantReadWriteLock rw = new ReentrantReadWriteLock();
private final Lock read = rw.readLock();
private final Lock write = rw.writeLock();
~~~

Đây là đoạn field **minh họa**, chưa phải một file Java độc lập. Nhớ đặt lock thành `private final` để không làm lộ khả năng đồng bộ nội bộ cho caller ngoài lớp.

### Ví dụ Java 17+: hai reader thực sự giữ khóa cùng lúc

Dùng latch để quan sát **đúng hai reader cùng giữ read lock**, thay vì dựa vào thời gian ngủ không xác định.

~~~java
// ConcurrentReadersDemo.java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class ConcurrentReadersDemo {
    public static void main(String[] args) throws InterruptedException {
        ReentrantReadWriteLock rw = new ReentrantReadWriteLock();
        CountDownLatch entered = new CountDownLatch(2);
        CountDownLatch release = new CountDownLatch(1);

        Runnable reader = () -> {
            rw.readLock().lock();
            try {
                entered.countDown();
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            } finally {
                rw.readLock().unlock();
            }
        };

        Thread first = new Thread(reader, "reader-1");
        Thread second = new Thread(reader, "reader-2");
        first.start();
        second.start();

        entered.await();
        System.out.println("Readers holding: " + rw.getReadLockCount());
        release.countDown();

        first.join();
        second.join();
        System.out.println("Readers after: " + rw.getReadLockCount());
    }
}
~~~

~~~bash
javac ConcurrentReadersDemo.java
java ConcurrentReadersDemo
~~~

Stdout:

~~~text
Readers holding: 2
Readers after: 0
~~~

Khi main đợi `entered.await()` thành công, cả hai reader đã lấy read lock, rồi cùng đợi `release` trước khi có thể nhả khóa. Do đó giá trị 2 ở điểm in là xác định. Sau khi nhả latch và `join` cả hai thread, không còn ai giữ read lock, nên kết quả là 0.

**Lưu ý:** `getReadLockCount()` là API quan sát/giám sát; không nên dùng nó như điều kiện để quyết định tính đúng của giao thức đồng bộ trong ứng dụng. Ví dụ dùng latch để cố định một trạng thái minh họa, không dựa vào việc hỏi số reader để thực hiện update.

### Quy tắc lock/unlock

~~~java
read.lock();
try {
    // Chỉ đọc dữ liệu được bảo vệ.
} finally {
    read.unlock();
}

write.lock();
try {
    // Đọc, kiểm tra và thay đổi bất biến.
} finally {
    write.unlock();
}
~~~

Đây là **các đoạn minh họa**, giả sử `read` và `write` đã khai báo. Thao tác `unlock` phải được thực hiện bởi thread hiện đang sở hữu số lần giữ khóa tương ứng. `ReentrantReadWriteLock` đếm các lần giữ lại (reentrancy); mỗi lần `lock` thành công phải được cân bằng bằng một lần `unlock`. Nếu unlock sai ownership có thể ném `IllegalMonitorStateException`.

## 3. Nâng cấp read → write: không được hỗ trợ

Tình huống thường gặp: thread đọc cache dưới read lock, phát hiện cache thiếu/hết hạn và muốn **giữ read lock rồi xin write lock** để cập nhật. Điều này không hoạt động.

~~~java
// CẤM áp dụng cách này; mã minh họa có thể tự chặn vô hạn.
rw.readLock().lock();
try {
    if (cacheNeedsRefresh()) {
        rw.writeLock().lock(); // Chờ vô hạn nếu thread vẫn giữ read lock.
        try {
            refreshCache();
        } finally {
            rw.writeLock().unlock();
        }
    }
} finally {
    rw.readLock().unlock();
}
~~~

Ở đây `cacheNeedsRefresh()` và `refreshCache()` là tên minh họa, **không phải API Java có sẵn**; đoạn code không phải file chạy độc lập.

### 3.1. Vì sao có thể tự deadlock kể cả khi chỉ một reader?

Thread T hiện giữ read lock. Để lấy write lock, không được có reader nào đang giữ read lock (ngoại trừ trường hợp chủ thread đã sở hữu write lock từ trước và nay lấy read lock). Thread T đang là chính reader khiến writer không được cấp quyền; nhưng code của T lại chờ `write.lock()` trả về **trước khi nhả read lock**. Nó tự chặn tiến triển của mình.

~~~text
Thread T:
  read.lock()   -> đã giữ read
  write.lock()  -> đợi tất cả read holders nhả read
  read.unlock() -> nằm sau write.lock(), không bao giờ tới được

=> Self-deadlock / chờ chuyển đổi khóa không thể hoàn tất.
~~~

Điểm này **không được sửa bằng fairness=true**, không được sửa bằng `volatile` hay thay thứ tự `finally`. Việc `ReentrantReadWriteLock` **reentrant** chỉ có nghĩa thread có thể tái nhập các lock theo chiều được hỗ trợ; nó **không** có chế độ upgrade dành cho một reader duy nhất.

### 3.2. Kiểm chứng bằng tryLock không làm chương trình treo

~~~java
// UpgradeAttemptDemo.java
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class UpgradeAttemptDemo {
    public static void main(String[] args) {
        ReentrantReadWriteLock rw = new ReentrantReadWriteLock();

        rw.readLock().lock();
        try {
            boolean upgraded = rw.writeLock().tryLock();
            System.out.println("Upgrade while holding read: " + upgraded);
            if (upgraded) {
                rw.writeLock().unlock();
            }
        } finally {
            rw.readLock().unlock();
        }

        boolean acquired = rw.writeLock().tryLock();
        System.out.println("Acquire after release: " + acquired);
        if (acquired) {
            rw.writeLock().unlock();
        }
    }
}
~~~

~~~bash
javac UpgradeAttemptDemo.java
java UpgradeAttemptDemo
~~~

Stdout:

~~~text
Upgrade while holding read: false
Acquire after release: true
~~~

Ngay cả khi không có thread khác, `tryLock()` cho write lock trả `false` trong lúc chính caller chỉ giữ read lock. Sau khi nhả read lock, caller lấy write lock thành công trong chương trình chỉ một thread này.

**Không dùng `write.lock()` để làm thí nghiệm cố tình self-deadlock**: chương trình sẽ bị kẹt và có thể cần dừng từ bên ngoài. Với giao thức nâng cấp sai trong ứng dụng thật, xem thread dump và các hold-count/stack trace để tìm điểm thread cố lấy write khi vẫn giữ read.

## 4. Thay nâng cấp bằng nhả read → lấy write → kiểm tra lại

Nếu cần “đọc trước, có vấn đề mới sửa”, mẫu đúng là:

1. Lấy read lock để quan sát trạng thái.
2. Nếu cần cập nhật, **nhả toàn bộ read hold thuộc caller** trước khi xin write lock.
3. Lấy write lock.
4. **Kiểm tra lại điều kiện** vì thread khác có thể đã cập nhật sau thời điểm nhả read.
5. Nếu vẫn cần, thực hiện cập nhật trong write lock, rồi nhả write lock.
6. Nếu cần tiếp tục đọc trạng thái được bảo vệ, lấy lại read lock hoặc dùng downgrade theo mục tiếp theo.

Vì có khoảng trống giữa nhả read và lấy write, không được lấy dữ liệu đọc lúc đầu làm bằng chứng rằng điều kiện vẫn đúng.

### Ví dụ cache khởi tạo đúng một lần

~~~java
// CacheInitializationDemo.java
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class CacheInitializationDemo {
    static final class Cache {
        private final ReentrantReadWriteLock rw =
            new ReentrantReadWriteLock();
        private String value;
        private int rebuildCount;

        String get() {
            rw.readLock().lock();
            try {
                if (value != null) {
                    return value;
                }
            } finally {
                rw.readLock().unlock();
            }

            // Khoảng trống: thread khác có thể khởi tạo cache tại đây.
            rw.writeLock().lock();
            try {
                if (value == null) { // BẮT BUỘC recheck.
                    value = "ready";
                    rebuildCount++;
                }
                return value;
            } finally {
                rw.writeLock().unlock();
            }
        }

        int rebuildCount() {
            rw.readLock().lock();
            try {
                return rebuildCount;
            } finally {
                rw.readLock().unlock();
            }
        }
    }

    public static void main(String[] args) throws InterruptedException {
        Cache cache = new Cache();
        Thread a = new Thread(cache::get, "A");
        Thread b = new Thread(cache::get, "B");
        a.start();
        b.start();
        a.join();
        b.join();

        System.out.println("Value: " + cache.get());
        System.out.println("Rebuilds: " + cache.rebuildCount());
    }
}
~~~

~~~bash
javac CacheInitializationDemo.java
java CacheInitializationDemo
~~~

Stdout:

~~~text
Value: ready
Rebuilds: 1
~~~

Dù A và B có thể đồng thời nhìn thấy `value == null` khi đang giữ read lock, sau khi nhả read, họ phải giành write lock từng người một. Thread nhận write lock đầu tiên gán `"ready"`; thread tiếp theo **kiểm tra lại** và không xây lại dữ liệu. Dòng `rebuildCount++` chỉ chạy khi `value` thực sự còn null bên trong write lock.

**Sai lầm:** chỉ đọc `if (value == null)` dưới read lock, nhả read rồi viết ngay dưới write **mà không kiểm tra lại**. Điều này có thể thực hiện tính toán cập nhật dư thừa, ghi đè phiên bản mới, hoặc làm side effect hai lần. Nếu việc xây lại cache thực hiện I/O tốn thời gian, cần cân nhắc thiết kế ownership/đồng bộ riêng và tránh giữ write lock quá lâu; không thể tự bỏ recheck để tối ưu.

### Khác biệt với một phép upgrade thật sự

Mẫu trên **không phải atomic upgrade**: giữa hai lần khóa, thread khác có quyền thay đổi trạng thái. Nhờ recheck, ta giữ đúng điều kiện cập nhật trong write lock; nhưng không giữ nguyên snapshot quan sát dưới read lock. Nếu nghiệp vụ đòi hỏi chuyển read→write không mất quyền giữa chừng, cần thiết kế lại giao thức (ví dụ giữ write từ đầu, CAS trên trạng thái bất biến hoặc primitive khác với hợp đồng chuyển đổi phù hợp).

## 5. Hạ cấp write → read: được hỗ trợ

**Downgrade** nghĩa là một thread đang giữ write lock muốn chuyển sang **tiếp tục đọc ổn định** mà không để writer khác chen vào giữa lúc nhả write và lấy read. `ReentrantReadWriteLock` hỗ trợ theo thứ tự:

~~~text
(1) write.lock()       -- thread có quyền ghi độc quyền
(2) update state       -- cập nhật dữ liệu
(3) read.lock()        -- chính writer được lấy thêm read
(4) write.unlock()     -- nhả quyền ghi, vẫn giữ read
(5) read state         -- writer khác không thể sửa khi read còn giữ
(6) read.unlock()      -- nhả quyền đọc
~~~

Bước **(3) phải trước bước (4)**. Nếu nhả write trước khi lấy read, một writer khác có thể giành write lock và sửa dữ liệu; khi ấy không còn bảo đảm quan sát đúng phiên bản vừa ghi.

### 5.1. Ví dụ Java 17+ đầy đủ

~~~java
// DowngradeDemo.java
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class DowngradeDemo {
    public static void main(String[] args) {
        ReentrantReadWriteLock rw = new ReentrantReadWriteLock();
        int[] data = {0}; // Chỉ để demo dữ liệu chia sẻ.

        rw.writeLock().lock();
        try {
            data[0] = 42;
            rw.readLock().lock(); // Writer được phép lấy read lock.
        } finally {
            rw.writeLock().unlock();
        }

        // Tới đây thread giữ read, không còn giữ write.
        try {
            System.out.println("Value under read lock: " + data[0]);
            System.out.println(
                "Read holds: " + rw.getReadHoldCount());
            System.out.println(
                "Write holds: " + rw.getWriteHoldCount());
        } finally {
            rw.readLock().unlock();
        }

        System.out.println("Read holds after: " + rw.getReadHoldCount());
    }
}
~~~

~~~bash
javac DowngradeDemo.java
java DowngradeDemo
~~~

Stdout:

~~~text
Value under read lock: 42
Read holds: 1
Write holds: 0
Read holds after: 0
~~~

Trong cùng thread, sau `rw.readLock().lock()` và `rw.writeLock().unlock()`, read hold vẫn còn. Phương thức `getReadHoldCount()` trả số read hold của chính thread đang gọi, khác với `getReadLockCount()` đo tổng số read hold trên cấu trúc lock. `getWriteHoldCount()` là số write hold reentrant của chính thread.

Bài demo có một thread nên dễ quan sát, nhưng thứ tự hạ cấp cũng đúng khi nhiều thread: một writer khác không thể nắm write lock trong lúc read lock còn được giữ. Các phương thức hold count dùng cho theo dõi/chẩn đoán, **không phải primitive để quyết định giao thức synchronization**.

### 5.2. Quản lý exception đúng khi có hai lock

Nếu code thực tế phức tạp, việc nhận read lock khi vẫn giữ write và nhả từng khóa ở các scope khác nhau dễ tạo lỗi:

- Nếu chưa nhận được read lock mà đã nhả write, không được giả định caller đang giữ read.
- Nếu đã nhận read lock, phải có `finally` tương ứng để nhả read khi không còn cần.
- Nếu đang giữ nhiều write hold do reentrancy, phải nhả đủ số write hold mới thực sự hết quyền ghi.
- Không chuyển ownership của lock cho thread khác; thread lấy khóa chịu trách nhiệm nhả khóa tương ứng.

Có thể gói chuyển trạng thái vào một abstraction nội bộ đã kiểm thử thay vì để nhiều caller tự tái hiện chuỗi hạ cấp.

## 6. Kết hợp double-check với downgrade cho cache

Một ứng dụng phổ biến: đọc cache; nếu không hợp lệ, yêu cầu quyền ghi để làm mới; sau đó tiếp tục xử lý dữ liệu dưới read lock.

~~~text
read.lock
  cache valid? -- yes --> use under read --> read.unlock
       |
       no
       v
read.unlock
write.lock
  recheck valid? -- no --> refresh
  read.lock (downgrade)
write.unlock
  use under read
read.unlock
~~~

Đoạn sau là **mẫu code minh họa** trong class có field `ReentrantReadWriteLock rw`, `boolean valid` và `Object data`. Giả sử `refresh()` tạo dữ liệu mà các reader cần; không phải file Java độc lập.

~~~java
Object useCache() {
    rw.readLock().lock();
    try {
        if (valid) {
            return data;
        }
    } finally {
        rw.readLock().unlock();
    }

    rw.writeLock().lock();
    try {
        if (!valid) { // Điều kiện phải được kiểm tra lại.
            data = refresh();
            valid = true;
        }
        rw.readLock().lock(); // Giữ read trước khi nhả write.
    } finally {
        rw.writeLock().unlock();
    }

    try {
        return data;
    } finally {
        rw.readLock().unlock();
    }
}
~~~

Cách này **hạ cấp đúng chiều** và không cho writer khác chen vào giữa việc làm mới với lúc bắt đầu đọc phiên bản mới. Nếu `refresh()` ném exception **trước khi lấy read lock**, block `finally` nhả write và ngoại lệ truyền ra; code sẽ không chạy tới đoạn đọc cuối. Với tác vụ phức tạp, cân nhắc việc giá trị `data` mutable có được sửa bên ngoài khóa hay không: trả reference rồi dùng nó sau khi nhả read lock có thể không còn snapshot ổn định nếu object tiếp tục bị writer sửa. Có thể trả bản bất biến, sao chép dữ liệu dưới khóa hoặc giữ xử lý cần nhất quán hoàn toàn trong phạm vi read lock.

**Điểm tinh tế:** hàm trên trả reference trong khối `try`, nhưng `finally` nhả read lock trước khi caller nhận và sử dụng object. Nếu caller cần truy cập nhiều thuộc tính mutable nhất quán sau đó, chỉ trả reference **chưa đủ**; cần có hợp đồng bất biến hoặc copy.

## 7. Reentrancy không phải upgrade

`ReentrantReadWriteLock` cho phép cùng thread:

- Đang giữ **read** tiếp tục `read.lock()` và phải `unlock()` đúng số lần.
- Đang giữ **write** tiếp tục `write.lock()`, tăng write hold count.
- Đang giữ **write** lấy thêm **read**; đây là cơ sở của downgrade.

Nó **không cho** thread chỉ đang giữ read nâng lên write. Ngay cả khi tự nghĩ mình “đang là reader duy nhất”, việc yêu cầu write có thể bị kẹt vì chính read hold của thread đó.

Đừng áp dụng trực giác “ReentrantLock cho phép cùng thread lấy lại khóa” cho một chuyển đổi **read → write**: hai quyền này khác nhau.

### Cùng thread giữ read và write, có phải writer khác được phép chạy?

Không. Khi thread chủ đang giữ write, các reader/writer khác bị chặn. Khi thread chủ nhả hết write nhưng còn read, các reader khác có thể cùng vào (tùy fairness), còn writer khác chưa thể sửa dữ liệu. Chính sự chuyển dịch quyền này tạo ra nghĩa của downgrade.

### Tại sao cần nhả đúng số lần?

Ví dụ minh họa:

~~~java
rw.writeLock().lock();
rw.writeLock().lock();
try {
    // Write hold count = 2 trong cùng thread.
} finally {
    rw.writeLock().unlock();
    rw.writeLock().unlock();
}
~~~

Nếu bỏ một lần unlock, thread vẫn giữ write lock và có thể chặn mọi reader/writer khác, tạo lỗi liveness rất khó phát hiện. Đoạn này không phải file độc lập; `rw` giả định đã được khai báo.

## 8. Fairness, tryLock và khả năng đói tài nguyên

### 8.1. Hai chế độ

~~~java
ReentrantReadWriteLock nonfair = new ReentrantReadWriteLock();
ReentrantReadWriteLock fair = new ReentrantReadWriteLock(true);
~~~

**Nonfair (mặc định):** thứ tự cấp quyền không được bảo đảm; thông lượng thường cao hơn, nhưng khi liên tục tranh chấp, reader hoặc writer có thể bị trì hoãn rất lâu, thậm chí vô thời hạn.

**Fair:** JDK áp dụng chính sách **xấp xỉ theo thứ tự đến** cho các thread đang tranh chấp, nhóm reader và writer dựa vào những người đang chờ lâu nhất. Fair mode có thể giảm nguy cơ starvation, nhưng có thêm overhead và **không bảo đảm fairness của scheduler**, cũng không cho một deadline cụ thể cho mọi tác vụ.

Quan trọng: **`readLock().tryLock()` và `writeLock().tryLock()` không tham gia chính sách fair** theo cách chờ thông thường; chúng có thể lập tức lấy khóa nếu khả dụng, dù có thread đang chờ (barging). Với yêu cầu tuân thủ fair khi thử không chờ, các overload `tryLock(0, TimeUnit.SECONDS)` có semantics gần tương ứng và xử lý interrupt.

### 8.2. Đừng chọn lock chỉ bằng nhãn fair

Các yếu tố cần đo:
- Tỷ lệ read/write, thời gian giữ từng lock, mức contention.
- Độ lớn công việc trong critical section.
- Cần deadline cho tác vụ không? `tryLock(timeout, unit)` hay `lockInterruptibly()` có thể hữu ích.
- Độ trễ tail, khả năng writer bị đói, overhead khi chuyển đổi hoặc recheck.

Một read/write lock có thể chậm hơn `synchronized` hoặc `ReentrantLock` thường nếu critical section rất nhỏ, số reader thấp, write thường xuyên hoặc contention lớn. Ưu thế nhiều reader song song chỉ có giá trị khi **đọc đủ nhiều và phần việc dưới read lock đủ đáng kể**.

### 8.3. Interrupt và timeout

`readLock()` và `writeLock()` đều hỗ trợ `lockInterruptibly()`/`tryLock(timeout, unit)`. Không được `unlock()` nếu không lấy được khóa:

~~~java
// Mã minh họa: write là Lock đã khai báo.
if (write.tryLock(100, java.util.concurrent.TimeUnit.MILLISECONDS)) {
    try {
        // Thực hiện cập nhật.
    } finally {
        write.unlock();
    }
} else {
    // Hết thời hạn mà chưa nhận write lock.
}
~~~

Phương thức trong đoạn minh họa phải khai báo hoặc xử lý `InterruptedException`. Timeout không hứa sẽ có quyền ghi, nên caller phải có phương án hủy, retry hoặc báo không hoàn thành theo nhu cầu.

## 9. Conditions: chỉ write lock hỗ trợ

Một sự khác biệt quan trọng với `ReentrantLock` đơn lẻ là **Condition**:

~~~java
ReentrantReadWriteLock rw = new ReentrantReadWriteLock();
Condition condition = rw.writeLock().newCondition(); // Hợp lệ.
rw.readLock().newCondition(); // UnsupportedOperationException.
~~~

Trong đoạn minh họa trên, cần import `java.util.concurrent.locks.Condition` nếu dùng trong file thật. `Condition` tạo từ write lock có hợp đồng điều kiện tương tự `ReentrantLock`; thông thường chỉ gọi `await()`/`signal()` khi đang giữ đúng write lock liên quan. `readLock().newCondition()` **không được hỗ trợ**.

### Ví dụ độc lập kiểm tra giới hạn

~~~java
// ConditionSupportDemo.java
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class ConditionSupportDemo {
    public static void main(String[] args) {
        ReentrantReadWriteLock rw = new ReentrantReadWriteLock();
        Condition valid = rw.writeLock().newCondition();
        System.out.println("Write condition created: " + (valid != null));

        try {
            rw.readLock().newCondition();
            System.out.println("Unexpected support");
        } catch (UnsupportedOperationException e) {
            System.out.println("Read condition unsupported");
        }
    }
}
~~~

~~~bash
javac ConditionSupportDemo.java
java ConditionSupportDemo
~~~

Stdout:

~~~text
Write condition created: true
Read condition unsupported
~~~

Nếu cần điều kiện chờ nhiều reader/writer phối hợp, nên thiết kế rõ predicate và lock sở hữu condition. Khi dùng `await()`, luôn kiểm tra lại predicate trong vòng `while` vì có thể thức dậy mà điều kiện chưa đúng; đừng đồng bộ bằng cách đợi condition của read lock vốn không tồn tại.

## 10. So sánh với ReentrantLock, StampedLock và concurrent collections

| Công cụ | Điểm mạnh | Điều cần chú ý |
| --- | --- | --- |
| `ReentrantLock` | Mutual exclusion đơn giản, reentrant, condition và nhiều kiểu chờ | Không cho các reader đồng thời trong critical section |
| `ReentrantReadWriteLock` | Nhiều reader đồng thời, writer độc quyền, **downgrade write→read** | **Không upgrade read→write**, overhead/fairness/conditions |
| `StampedLock` (JDK 8+) | Read/write stamps, optimistic reads, một số `tryConvertToWriteLock`/`tryConvertToReadLock` | **Không reentrant**; conversion có thể thất bại; optimistic read bắt buộc validate, không coi stamp là monitor thông thường |
| `ConcurrentHashMap` | Cung cấp thao tác concurrent trên map, một số API atomic theo key | Chuỗi thao tác của caller không tự atomic; đọc/ghi nhiều key có thể cần thiết kế bổ sung |
| Immutable snapshot với atomic reference | Reader lấy phiên bản bất biến, writer thay reference nguyên tử | Logic cập nhật nhiều writer phải dùng CAS; object phải thực sự bất biến |

**StampedLock không phải một cách “bật upgrade” cho ReentrantReadWriteLock.** Nó là primitive khác với hợp đồng khác. `tryConvertToWriteLock(stamp)` có thể thất bại khi không thể chuyển quyền; caller phải xử lý thất bại, bao gồm nhả stamp cũ đúng cách và có thể thử chiến lược mới. `StampedLock` cũng không reentrant và optimistic read không đảm bảo snapshot hợp lệ nếu không xác thực bằng `validate`.

Nếu logic chỉ cần một lần đọc/ghi nhanh trên map, API atomic của collection có thể đơn giản hơn một lock lớn. Nhưng việc lựa chọn phải theo **bất biến**, không chỉ theo số lượng reader.

## 11. Những lỗi phổ biến

- **“Đang là reader duy nhất thì read.lock → write.lock được.”** Sai: việc nâng cấp trực tiếp không được hỗ trợ, có thể tự chặn vô hạn.
- **“Fair=true sửa lỗi upgrade.”** Sai: fairness không thay đổi quy tắc sở hữu/upgrade.
- **“Nhả read rồi lấy write là atomic upgrade.”** Sai: thread khác có thể thay đổi dữ liệu trong khoảng trống, bắt buộc recheck.
- **“write.unlock() rồi read.lock() là downgrade an toàn.”** Sai: writer khác có thể chen vào giữa hai lời gọi.
- **“Reentrant nghĩa là unlock một lần sau nhiều lần lock.”** Sai: phải cân bằng số lần giữ lock.
- **“Chỉ writer cần khóa; reader đọc field thường ở ngoài cũng được.”** Sai: reader phải dùng cùng giao thức để thấy dữ liệu/snapshot đúng.
- **“readLock.newCondition() dùng được như writeLock.newCondition().”** Sai: read condition ném `UnsupportedOperationException`.
- **“tryLock tuân thủ hoàn toàn fair=true.”** Sai với untimed `tryLock()`.
- **“ReadWriteLock luôn nhanh hơn synchronized.”** Không có bảo đảm; cần đo theo workload.
- **“getReadLockCount() là primitive để quyết định nâng cấp.”** Sai: đây là số liệu theo dõi, không tạo quyền chuyển khóa nguyên tử.
- **“Đã hạ cấp thì reader khác không bao giờ vào.”** Sai: sau khi nhả write và còn read, những reader khác có thể được phép đồng thời đọc (tùy policy); writer khác vẫn chưa thể ghi.
- **“Giữ khóa trong lúc gọi mã ngoài lâu cũng không ảnh hưởng.”** Sai: có thể tăng contention, latency và deadlock.

## 12. Quy trình kiểm tra code

1. **Chỉ ra trạng thái chia sẻ và invariant:** cache, map, bộ đếm, các field phải đọc nhất quán.
2. **Đánh dấu đoạn read-only và đoạn write:** có thao tác nào trong read section thực ra làm thay đổi object mutable không?
3. **Tìm dấu hiệu upgrade:** code giữ `readLock` rồi gọi `writeLock.lock`/`lockInterruptibly` hoặc `tryLock`? Nếu có, thiết kế lại nhả read và recheck.
4. **Tìm dấu hiệu downgrade:** có lấy **read trước khi nhả write** không? Có nhả read cuối cùng trong `finally` không?
5. **Kiểm tra reentrant hold count:** có nhiều lần lock nhưng thiếu unlock? Caller đã giữ một khóa từ scope bên ngoài chưa?
6. **Đảm bảo mọi reader/writer dùng cùng rw instance:** đừng tạo lock mới trên mỗi lời gọi hoặc trả reference lock ra API khi không chủ ý.
7. **Kiểm tra fairness và liveness:** nonfair có nguy cơ trì hoãn, fair có overhead, timed tryLock cần xử lý timeout/interrupt.
8. **Kiểm tra Condition:** chỉ viết condition từ write lock, predicate kiểm tra trong vòng `while`.
9. **Đo hành vi:** so throughput/latency so với `ReentrantLock`/`synchronized` dưới workload thực tế; không mặc định read/write lock sẽ tốt hơn.
10. **Dùng thread dump khi bị kẹt:** phân biệt thread đang chờ upgrade, deadlock do nhiều lock, hay contention bình thường.

## 13. Tự kiểm tra

**1.** Thread T đang giữ read lock, là reader duy nhất. Gọi `writeLock().lock()` có upgrade thành công không?  
**Đáp án:** Không. `ReentrantReadWriteLock` không hỗ trợ nâng cấp read→write; code có thể tự chờ vô hạn.

**2.** Sau khi phát hiện cache không hợp lệ dưới read lock, vì sao phải kiểm tra lại khi đã lấy write lock?  
**Đáp án:** Vì trong khoảng nhả read và chờ write, thread khác có thể đã làm mới cache; điều kiện cũ không còn đáng tin.

**3.** Cần đọc ngay phiên bản vừa ghi mà không cho writer khác chen vào. Thứ tự đúng?  
**Đáp án:** `write.lock → cập nhật → read.lock → write.unlock → đọc → read.unlock`.

**4.** `rw.writeLock().newCondition()` và `rw.readLock().newCondition()` khác gì?  
**Đáp án:** Write lock hỗ trợ `Condition`; read lock ném `UnsupportedOperationException`.

**5.** Với `new ReentrantReadWriteLock(true)`, `tryLock()` có tôn trọng hoàn toàn chính sách fair không?  
**Đáp án:** Không. Untimed `tryLock()` có thể barging khi khóa khả dụng.

**6.** Nếu chỉ có đọc rất ngắn và ghi thường xuyên, read/write lock chắc chắn nhanh hơn `synchronized`?  
**Đáp án:** Không; overhead quản lý readers/writer có thể cao hơn lợi ích. Cần benchmark thực tế.

**7.** Nếu thread giữ write lock rồi lấy read lock, nhả write thì thread đó còn giữ quyền nào?  
**Đáp án:** Còn read lock; có thể đọc tiếp. Writer khác không được cập nhật cho tới khi toàn bộ read holds liên quan được nhả.

**8.** Dùng `StampedLock.tryConvertToWriteLock` có luôn nâng cấp thành công?  
**Đáp án:** Không. Conversion có thể trả 0 khi không thể đổi quyền; phải xử lý thất bại và vòng đời stamp đúng cách.

**9.** Một thread đọc `Map` mà không giữ read lock, trong khi writer cập nhật dưới write lock. Đã thread-safe chưa?  
**Đáp án:** Chưa, nếu map là mutable và không có giao thức đồng bộ khác. Reader phải tuân thủ lock hoặc dùng collection/thiết kế khác có bảo đảm phù hợp.

**Ghi nhớ:** `ReentrantReadWriteLock` chia quyền **nhiều reader / một writer**. **Upgrade read→write không hỗ trợ**; nhả read rồi lấy write phải **recheck**. **Downgrade write→read có hỗ trợ**, nhưng phải **lấy read trước khi nhả write**. Tính đúng phụ thuộc bất biến và mọi đường truy cập; hiệu năng, fairness, conditions và reentrancy là những giới hạn cần kiểm chứng.

### Tài liệu tham khảo chuẩn

- Java 17 `ReentrantReadWriteLock` (reentrancy, downgrading, fairness, conditions): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html
- Java 17 `ReadWriteLock` (memory consistency, sharing semantics): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReadWriteLock.html
- Java 17 `Lock`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/Lock.html
- Java 17 `StampedLock`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/StampedLock.html