# Quy tắc độc quyền của khóa ghi

## 1. Vì sao một người ghi phải ngăn cả người đọc?

Giả sử trạng thái chia sẻ gồm hai số dư. Chuyển tiền cần giảm số dư bên A và tăng số dư bên B. Nếu người đọc nhìn dữ liệu ở giữa hai câu lệnh, họ có thể thấy tổng tiền bị giảm tạm thời dù thuật toán chuyển tiền sẽ bù lại ngay sau đó.

Khóa ghi của ReadWriteLock cung cấp một khoảng xử lý độc quyền để những luồng tuân theo cùng giao thức khóa không nhìn hoặc sửa trạng thái giữa chừng.

Cần phân biệt:

- **Đọc:** chỉ quan sát trạng thái, không làm thay đổi dữ liệu được bảo vệ.
- **Ghi:** thay đổi trạng thái, gồm cả phép cập nhật nhiều bước.
- **Cặp khóa liên quan:** readLock và writeLock được lấy từ cùng một ReadWriteLock.
- **Vùng được bảo vệ:** phần mã thực sự giữ khóa trong lúc dùng dữ liệu.

Khóa không tự biết trường dữ liệu nào thuộc nó. Quy tắc chỉ có tác dụng khi mọi đường truy cập đều dùng đúng cặp khóa.

Bài dùng ReentrantReadWriteLock trên Java 17+ để minh họa cơ chế vẫn áp dụng trong Java hiện đại.

## 2. Ma trận tương thích giữa các luồng khác nhau

Xét yêu cầu lấy khóa của một **luồng khác**:

| Trạng thái đang có | Luồng khác xin readLock | Luồng khác xin writeLock |
| --- | --- | --- |
| Có một hoặc nhiều người đọc, chưa có người ghi | Có thể đọc cùng, tùy chính sách cấp khóa | Phải chờ người đọc nhả hết |
| Có người ghi giữ writeLock | Phải chờ | Phải chờ |
| Không có người đọc/ghi giữ khóa | Có thể lấy theo chính sách | Có thể lấy theo chính sách |

“Có thể” không phải lời hứa chắc chắn lấy ngay nếu còn những luồng đang chờ và chính sách công bằng ảnh hưởng thứ tự cấp khóa.

Điểm cốt lõi: **chỉ một luồng sở hữu khóa ghi tại một thời điểm**, và khi luồng đó giữ quyền ghi, luồng khác không được giữ quyền đọc của cùng cặp khóa. [Tài liệu ReadWriteLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReadWriteLock.html)

Nhiều người đọc cùng lúc không ngăn cản nhau vì họ không được sửa dữ liệu. Người ghi phải chờ quyền đọc được nhả; chỉ chờ các người ghi khác là chưa đủ để giữ ảnh chụp nhất quán.

## 3. Độc quyền không có nghĩa Java ngăn mọi lệnh truy cập

Đây là một giao thức hợp tác giữa các luồng:

```text
Mọi phép đọc trạng thái -> lấy readLock, hoặc giữ writeLock khi đang cập nhật
Mọi phép sửa trạng thái -> lấy writeLock của cùng cặp khóa
```

Nếu một phương thức đọc trực tiếp trường dữ liệu mà không lấy khóa, writeLock không tự chặn phương thức đó. Nếu một nơi dùng synchronized trên đối tượng khác, nó cũng không tự tham gia cùng cơ chế.

Hai ReentrantReadWriteLock riêng biệt không bảo vệ lẫn nhau chỉ vì có cùng kiểu hoặc cùng tên biến. ReadLock từ đối tượng thứ nhất không phối hợp với WriteLock từ đối tượng thứ hai.

Vì vậy, thường nên đặt dữ liệu và cặp khóa trong cùng một lớp, giữ trường private và chỉ cung cấp các thao tác đúng giao thức.

Một thao tác có tên “get” vẫn cần quyền ghi nếu nó thực sự sửa bộ nhớ đệm, tăng bộ đếm thuộc cùng trạng thái hoặc biến đổi cấu trúc dữ liệu. Quyền khóa theo **hành vi**, không theo tên phương thức.

## 4. Ví dụ: bảo vệ bất biến của hai trường

Lớp dưới giữ hai phần của cùng một tổng. Mỗi bước chuyển một đơn vị từ right sang left và tăng version.

Tệp **ExclusiveStateDemo.java**:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class ExclusiveStateDemo {
    record Snapshot(int left, int right, int version) {}

    static final class Ledger {
        private final ReentrantReadWriteLock rw = new ReentrantReadWriteLock();
        private final Lock read = rw.readLock();
        private final Lock write = rw.writeLock();

        private int left = 0;
        private int right = 2000;
        private int version = 0;

        void moveOne() {
            write.lock();
            try {
                if (right <= 0) {
                    throw new IllegalStateException("No balance left");
                }
                right--;
                left++;
                version++;
            } finally {
                write.unlock();
            }
        }

        Snapshot snapshot() {
            read.lock();
            try {
                return new Snapshot(left, right, version);
            } finally {
                read.unlock();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Ledger ledger = new Ledger();
        ExecutorService pool = Executors.newFixedThreadPool(3);
        CountDownLatch start = new CountDownLatch(1);

        Callable<Void> writer = () -> {
            start.await();
            for (int i = 0; i < 1000; i++) {
                ledger.moveOne();
            }
            return null;
        };

        try {
            Future<Void> first = pool.submit(writer);
            Future<Void> second = pool.submit(writer);
            Future<Integer> reader = pool.submit(() -> {
                start.await();
                int valid = 0;
                for (int i = 0; i < 1000; i++) {
                    Snapshot value = ledger.snapshot();
                    if (value.left() + value.right() != 2000
                            || value.version() != value.left()) {
                        throw new AssertionError("Inconsistent snapshot");
                    }
                    valid++;
                }
                return valid;
            });

            start.countDown();
            first.get();
            second.get();
            int validSnapshots = reader.get();

            Snapshot result = ledger.snapshot();
            System.out.println("left=" + result.left());
            System.out.println("right=" + result.right());
            System.out.println("version=" + result.version());
            System.out.println("validSnapshots=" + validSnapshots);
        } finally {
            start.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor did not terminate");
            }
        }
    }
}
```

Chạy:

```shell
javac --release 17 ExclusiveStateDemo.java
java ExclusiveStateDemo
```

Stdout khi hoàn tất bình thường:

```text
left=2000
right=0
version=2000
validSnapshots=1000
```

Hai tác vụ ghi cùng thực hiện tổng cộng 2000 bước. WriteLock khiến các bước của những người ghi không chen vào vùng cập nhật của nhau; readLock khiến snapshot không nhìn vào giữa các câu lệnh cập nhật.

Một lần chạy đạt 1000 ảnh chụp không phải bằng chứng rằng mọi mã tương tự đều đúng. Lập luận đúng ở đây là mọi phép truy cập ba trường đều theo cùng cặp khóa và snapshot giữ quyền đọc trong suốt lúc sao chép.

Các tác vụ được mở cùng một chốt, nhưng lịch chạy vẫn do môi trường quyết định. Ví dụ không khẳng định mỗi ảnh chụp đều xảy ra đúng giữa hai lượt ghi.

## 5. Vì sao chỉ khóa từng phép gán là chưa đủ?

Nếu chương trình lấy/nhả writeLock quanh riêng `right--`, rồi lấy/nhả lại quanh `left++`, người đọc có thể lấy readLock ở khoảng giữa.

Ranh giới cần bảo vệ là **toàn bộ thao tác giữ bất biến**, không chỉ từng trường:

```text
writeLock
    kiểm tra điều kiện
    cập nhật right
    cập nhật left
    cập nhật version
unlock
```

Tương tự, một phương thức snapshot phải đọc cả các trường liên quan trong cùng một lần giữ readLock. Nếu gọi các getter lấy khóa riêng lẻ, mỗi getter có thể nhìn một phiên bản khác nhau.

Ví dụ total bằng cách gọi getLeft rồi getRight riêng có thể cộng giá trị trước và sau một cập nhật. Mỗi getter có khóa không tự làm cả chuỗi thao tác nguyên tử.

Đặt biến thành volatile cũng không thay thế việc giữ bất biến nhiều trường trong một giao thức khóa chung. Khả năng nhìn thấy từng giá trị và ảnh chụp nguyên tử của cả nhóm dữ liệu là hai yêu cầu khác nhau.

## 6. Chính luồng giữ writeLock có thể tái nhập

ReentrantReadWriteLock có các đặc điểm riêng:

- Luồng đã giữ writeLock có thể lấy lại writeLock.
- Luồng giữ writeLock có thể lấy readLock.
- Một luồng chỉ đang giữ readLock không thể nâng cấp trực tiếp thành writeLock bằng cách giữ nguyên quyền đọc rồi chờ.

Vì vậy, câu “khi có writeLock thì không ai lấy được readLock” cần thêm điều kiện **luồng khác**. Chính người ghi có thể lấy quyền đọc liên quan theo hợp đồng tái nhập. [Tài liệu ReentrantReadWriteLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html)

Tái nhập không tạo thêm một người ghi thứ hai. Nó tăng số lần giữ của cùng luồng; phải nhả đủ số lần tương ứng.

Nếu giữ writeLock hai lần nhưng chỉ unlock một lần, luồng khác vẫn chưa thể vào.

### Thí nghiệm quyền của chủ sở hữu và luồng khác

Tệp **WriteLockOwnershipDemo.java**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class WriteLockOwnershipDemo {
    record Probe(boolean readAcquired, boolean writeAcquired) {}

    private static Probe probe(ReentrantReadWriteLock rw) {
        Lock read = rw.readLock();
        Lock write = rw.writeLock();

        boolean gotRead = read.tryLock();
        if (gotRead) {
            read.unlock();
        }

        boolean gotWrite = write.tryLock();
        if (gotWrite) {
            write.unlock();
        }
        return new Probe(gotRead, gotWrite);
    }

    public static void main(String[] args) throws Exception {
        ReentrantReadWriteLock rw = new ReentrantReadWriteLock();
        ExecutorService other = Executors.newSingleThreadExecutor();
        Lock write = rw.writeLock();

        try {
            write.lock();
            try {
                write.lock();
                try {
                    System.out.println("ownerWriteHoldCount="
                            + rw.getWriteHoldCount());

                    boolean ownerCanRead = rw.readLock().tryLock();
                    try {
                        System.out.println("ownerCanRead=" + ownerCanRead);
                    } finally {
                        if (ownerCanRead) {
                            rw.readLock().unlock();
                        }
                    }

                    Probe blocked = other.submit(() -> probe(rw)).get();
                    System.out.println("otherReadDuringWrite="
                            + blocked.readAcquired());
                    System.out.println("otherWriteDuringWrite="
                            + blocked.writeAcquired());
                } finally {
                    write.unlock();
                }

                Future<Probe> stillHeld = other.submit(() -> probe(rw));
                System.out.println("otherWriteAfterOneUnlock="
                        + stillHeld.get().writeAcquired());
            } finally {
                write.unlock();
            }

            Probe available = other.submit(() -> probe(rw)).get();
            System.out.println("otherReadAfterRelease="
                    + available.readAcquired());
            System.out.println("otherWriteAfterRelease="
                    + available.writeAcquired());
        } finally {
            other.shutdownNow();
            if (!other.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor did not terminate");
            }
        }
    }
}
```

Chạy:

```shell
javac --release 17 WriteLockOwnershipDemo.java
java WriteLockOwnershipDemo
```

Stdout:

```text
ownerWriteHoldCount=2
ownerCanRead=true
otherReadDuringWrite=false
otherWriteDuringWrite=false
otherWriteAfterOneUnlock=false
otherReadAfterRelease=true
otherWriteAfterRelease=true
```

TryLock trong luồng khác trả ngay nên chương trình không cần dùng sleep để đoán “luồng kia đang bị chặn”.

Ở probe, read và write được thử **lần lượt**, nhả read trước khi thử write. Hai giá trị true ở mốc cuối không nói luồng khác đang giữ đồng thời cả hai hoặc đã nâng cấp từ read sang write.

Main giữ quyền ghi trong lúc chờ kết quả probe, nhưng probe chỉ tryLock không chờ. Không đổi nó thành lock chặn rồi giữ nguyên cấu trúc chờ get: khi đó main chờ luồng cần chính khóa main đang giữ, tạo kẹt.

## 7. Lấy khóa đúng cách và luôn nhả trong finally

Mẫu cơ bản:

```java
write.lock();
try {
    updateSharedState();
} finally {
    write.unlock();
}
```

Đây là mã minh họa trong phương thức đã có write và updateSharedState. Lệnh lock nằm trước try; chỉ khi lấy thành công mới đi vào phạm vi phải unlock.

Với tryLock, chỉ unlock nếu kết quả là true. Với lockInterruptibly hoặc tryLock có timeout, lỗi ngắt/hết thời gian phải được xử lý theo hợp đồng; không unlock một khóa chưa lấy được.

Quyền sở hữu khóa thuộc luồng đã lấy nó. Không giao việc nhả writeLock cho một luồng khác. Với ReentrantReadWriteLock, nhả sai quyền có thể dẫn tới IllegalMonitorStateException.

Lock là một đối tượng bình thường, nhưng `synchronized(write)` lấy monitor của đối tượng đó, không tự lấy writeLock. Đừng trộn hai giao thức rồi mong chúng cùng tạo một vùng loại trừ. [Tài liệu Lock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/Lock.html)

## 8. Quyền ghi và khả năng nhìn thấy dữ liệu

Việc nhả writeLock rồi một luồng khác lấy readLock liên quan không chỉ điều phối ai được vào. ReadWriteLock còn có hợp đồng đồng bộ bộ nhớ: người đọc lấy thành công readLock nhìn thấy các cập nhật đã được công bố qua lần nhả writeLock trước.

Điều này giải thích vì sao snapshot trong ví dụ không cần đọc trực tiếp các trường volatile: các truy cập đều qua giao thức khóa.

Nhưng khóa không “đóng băng” đối tượng sau khi đã unlock. Nếu snapshot trả thẳng một List có thể sửa bên trong rồi người gọi dùng nó sau khi nhả khóa, người gọi vẫn có thể nhìn hoặc sửa dữ liệu ngoài phạm vi bảo vệ.

Ví dụ Ledger trả record chứa các giá trị int đã sao chép, nên không làm rò một đối tượng trạng thái bên trong có thể thay đổi. Với collection hoặc đối tượng lồng nhau, phải cân nhắc sao chép và tính bất biến của phần tử nữa.

Không dùng isWriteLocked hoặc getReadLockCount như bước kiểm tra rồi truy cập không khóa. Giá trị quan sát có thể đổi ngay; các phương thức theo dõi không cấp quyền sử dụng dữ liệu.

## 9. Độc quyền không phải ưu tiên tuyệt đối cho người ghi

Một người ghi phải đợi những người đọc đang giữ khóa nhả ra. Fairness ảnh hưởng thứ tự cấp quyền, không thay đổi quy tắc loại trừ.

ReentrantReadWriteLock mặc định không công bằng; thứ tự được cấp khi cạnh tranh không phải FIFO chắc chắn. Chế độ fair hỗ trợ chính sách gần với thứ tự đến, nhưng không làm vùng ghi dài biến mất.

Các tryLock không chờ có hành vi riêng với fairness; không suy ra mọi cách xin khóa đều tuân cùng hàng chờ như lock thông thường.

Nếu muốn tránh người ghi chờ quá lâu, hãy xem thời gian giữ readLock, số người đọc, chính sách cấp quyền và loại công việc trong vùng khóa. Không sửa dữ liệu dưới readLock chỉ để “đỡ chờ”.

Đừng nâng cấp bằng cách giữ readLock rồi gọi writeLock.lock. Với lớp này, cần nhả quyền đọc trước, lấy quyền ghi rồi kiểm tra lại điều kiện vì dữ liệu có thể đã thay đổi trong khoảng trống.

## 10. Giữ vùng ghi ngắn nhưng đủ giữ bất biến

Một vùng độc quyền dài làm cả người đọc và người ghi khác chờ. Tránh giữ writeLock trong lúc thực hiện thao tác mạng dài, gọi callback không kiểm soát hoặc chờ kết quả cần luồng khác tiến vào cùng dữ liệu.

Có thể chuẩn bị dữ liệu ngoài khóa rồi lấy writeLock để xác minh điều kiện và cập nhật ngắn. Nhưng nếu điều kiện đã thay đổi, phải xử lý lại; không dùng một ảnh chụp cũ như thể còn được bảo vệ.

Khóa cũng không tự hoàn tác dữ liệu nếu ngoại lệ xảy ra giữa cập nhật. Trong Ledger, phần cập nhật sau kiểm tra chỉ gồm các phép số học đơn giản. Với thao tác có thể ném lỗi giữa nhiều thay đổi, cần thiết kế xác thực trước, dữ liệu thay thế hoặc chiến lược khôi phục để không nhả khóa trong trạng thái sai.

Độc quyền đảm bảo không có luồng tuân thủ giao thức chen vào; nó không tự chứng minh thuật toán cập nhật đúng.

## 11. Tự đánh giá một vùng ghi

Khi đọc một phương thức cập nhật dữ liệu dùng ReadWriteLock, hãy xác định:

1. ReadLock và WriteLock có thuộc cùng đối tượng không?
2. Mọi đường đọc/ghi có dùng đúng giao thức không?
3. Vùng writeLock có bao trọn điều kiện và các cập nhật giữ bất biến không?
4. Giá trị trả ra có làm rò đối tượng có thể sửa ngoài khóa không?
5. Mỗi lần lấy khóa có lần nhả đúng quyền trong finally không?
6. Có chờ một luồng khác cần khóa mình đang giữ không?
7. Ngoại lệ giữa cập nhật có để lại trạng thái hợp lệ không?

Quy tắc độc quyền có ý nghĩa khi ranh giới dữ liệu, quyền truy cập và bất biến được mô tả cùng nhau. Khi đó, người ghi có thể cập nhật một trạng thái nhất quán và người đọc chỉ quan sát các phiên bản đã được công bố đúng cách.
