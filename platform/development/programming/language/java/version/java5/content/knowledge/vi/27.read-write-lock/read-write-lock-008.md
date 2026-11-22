# Condition gắn với khóa ghi

## 1. Khi khóa chưa đủ: cần chờ trạng thái thay đổi

Khóa trả lời câu hỏi: **luồng nào được truy cập dữ liệu lúc này?** Một điều kiện chờ trả lời câu hỏi khác: **khi nào dữ liệu đủ điều kiện để thao tác tiếp?** Ví dụ, một luồng muốn chờ đến khi cấu hình có phiên bản mới. Nó không nên giữ quyền ghi rồi lặp kiểm tra liên tục, vì người cập nhật sẽ không lấy được khóa để tạo ra phiên bản mới.

`Condition` cung cấp thao tác chờ và phát tín hiệu, gắn với một khóa cụ thể. Với `ReentrantReadWriteLock`, tạo nó bằng **`writeLock().newCondition()`**. Việc tạo đối tượng không đòi hỏi đang giữ ghi; khi thực hiện `await()`, `signal()` hoặc `signalAll()` thì luồng phải giữ chính khóa ghi đó. Xem [WriteLock.newCondition](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.WriteLock.html#newCondition()).

`readLock().newCondition()` không được hỗ trợ và ném `UnsupportedOperationException`. Chỉ đang giữ đọc không đủ để dùng điều kiện thuộc khóa ghi. Xem [ReadLock.newCondition](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.ReadLock.html#newCondition()).

Các quy tắc này vẫn áp dụng trong Java hiện hành. Ví dụ dưới đây dùng API chạy được trên JDK 17 trở lên.

## 2. Phân biệt đối tượng Condition và điều kiện của dữ liệu

Giả sử có biến `version` và người dùng muốn chờ `version >= expected`:

- `version >= expected` là **mệnh đề điều kiện**, tính từ dữ liệu được bảo vệ.
- `changed` là đối tượng `Condition`, quản lý việc chờ và đánh thức liên quan tới dữ liệu đó.
- Khóa ghi bảo vệ cả việc kiểm tra mệnh đề và việc thay đổi dữ liệu, phát tín hiệu.

Tên `changed` không tự gắn với biến `version`. JVM không tự phát hiện rằng phiên bản thay đổi để đánh thức người chờ; chương trình phải gọi tín hiệu đúng chỗ. `signalAll()` cũng không tự sửa dữ liệu cho thỏa điều kiện.

Một mẫu tối thiểu, minh họa bên trong lớp đã có `write`, `changed`, `version` và `expected`:

```java
write.lockInterruptibly();
try {
    while (version < expected) {
        changed.await();
    }
    // Tại đây đang giữ khóa ghi và điều kiện đã đúng.
} finally {
    write.unlock();
}
```

Người cập nhật cũng lấy `write`, thay đổi `version`, rồi gọi `changed.signalAll()` trong phạm vi giữ khóa.

## 3. Điều gì xảy ra tại await và signal?

Khi đang giữ ghi mà điều kiện chưa đúng, `await()` đưa luồng vào chờ đồng thời nhả khóa ghi. Luồng khác nhờ đó có thể lấy ghi và cập nhật dữ liệu. Trước khi lời gọi chờ kết thúc, người chờ phải lấy lại ghi. Với khóa ghi tái nhập, số lần giữ được khôi phục như trước khi chờ.

`signal()` chọn một người chờ để đánh thức; `signalAll()` đánh thức tất cả người đang chờ trên cùng đối tượng `Condition`. **Phát tín hiệu không nhả khóa ngay và không trao quyền chạy tiếp ngay.** Người phát vẫn giữ ghi cho đến `unlock()`; người được đánh thức còn phải cạnh tranh để lấy lại ghi.

Luôn kiểm tra điều kiện bằng `while`, vì có thể thức dậy giả (spurious wakeup), hoặc trạng thái không còn phù hợp khi lấy lại khóa. Xem [hợp đồng Condition](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/Condition.html).

Ví dụ với tài nguyên có thể bị tiêu thụ: hai người cùng chờ một phần tử mới. Sau `signalAll()`, người thứ nhất lấy được phần tử; người thứ hai khi lấy lại ghi phải thấy hàng đợi trống và tiếp tục chờ. Với `if`, người thứ hai có thể đi tiếp bằng một giả định đã hết đúng.

## 4. Ví dụ đầy đủ: chờ phiên bản dữ liệu

Lớp `VersionedValue` hỗ trợ ba đường truy cập:

| Phương thức | Quyền giữ khóa | Mục đích |
| --- | --- | --- |
| `snapshot()` | Đọc | Lấy bản chụp hiện tại, không chờ phiên bản |
| `publish()` | Ghi | Thay giá trị, tăng phiên bản, đánh thức người chờ |
| `awaitVersion()` | Ghi khi kiểm tra; nhả khi chờ | Đợi tới phiên bản mong muốn |

Dù `awaitVersion()` cuối cùng trả dữ liệu, nó vẫn dùng ghi vì `Condition` thuộc khóa ghi. Khi thực sự chờ, nó không giữ ghi. Kết quả là `Snapshot` bất biến chứa một `String`, có thể trả cho bên gọi sau khi nhả khóa.

Lưu thành `WriteConditionDemo.java`:

```java
import java.util.Objects;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.locks.Condition;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class WriteConditionDemo {
    record Snapshot(long version, String value) { }

    private static final class VersionedValue {
        private final ReentrantReadWriteLock rw = new ReentrantReadWriteLock();
        private final Condition changed = rw.writeLock().newCondition();
        private long version;
        private String value = "initial";

        Snapshot snapshot() {
            rw.readLock().lock();
            try {
                return new Snapshot(version, value);
            } finally {
                rw.readLock().unlock();
            }
        }

        void publish(String newValue) {
            Objects.requireNonNull(newValue);
            rw.writeLock().lock();
            try {
                value = newValue;
                version++;
                changed.signalAll();
            } finally {
                rw.writeLock().unlock();
            }
        }

        Snapshot awaitVersion(long expected, CountDownLatch aboutToAwait)
                throws InterruptedException {
            rw.writeLock().lockInterruptibly();
            try {
                while (version < expected) {
                    // Chỉ phục vụ phối hợp trong ví dụ chạy thử.
                    aboutToAwait.countDown();
                    changed.await();
                }
                return new Snapshot(version, value);
            } finally {
                rw.writeLock().unlock();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        VersionedValue state = new VersionedValue();
        Snapshot before = state.snapshot();
        System.out.println("before=" + before.version() + ":" + before.value());

        CountDownLatch aboutToAwait = new CountDownLatch(1);
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            Future<Snapshot> waiting =
                    pool.submit(() -> state.awaitVersion(1, aboutToAwait));
            aboutToAwait.await();
            state.publish("updated");
            Snapshot result = waiting.get();
            System.out.println("observed=" + result.version() + ":" + result.value());
            Snapshot after = state.snapshot();
            System.out.println("after=" + after.version() + ":" + after.value());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac -encoding UTF-8 WriteConditionDemo.java
java WriteConditionDemo
```

Stdout:

```text
before=0:initial
observed=1:updated
after=1:updated
```

`CountDownLatch` giúp phép thử biết luồng chờ đã kiểm tra điều kiện dưới ghi; nó không thay thế `Condition`. Sau `countDown()`, luồng chờ vẫn giữ ghi cho tới `await()`. Vì vậy `publish()` không thể chen vào giữa lần kiểm tra và việc đăng ký chờ: nó chỉ lấy được ghi khi `await()` đã nhả khóa. Ví dụ không dựa vào `Thread.sleep()` hay đoán lịch chạy.

Trong mã ứng dụng, có thể bỏ tham số `aboutToAwait` và dòng `countDown()`. Vòng `while`, khóa ghi và `changed.await()` vẫn giữ nguyên. Không chờ một `Future` cần cùng khóa trong lúc đang giữ khóa đó.

## 5. Vì sao tín hiệu đến sớm không bị hiểu thành giấy phép?

`Condition` không lưu tín hiệu như bộ đếm giấy phép của `Semaphore`. Nếu không ai đang chờ, `signalAll()` không tạo một tín hiệu để người đến sau nhận.

Trong ví dụ, nếu `publish()` chạy **trước** khi `awaitVersion()` lấy ghi, người đến sau thấy `version >= expected` và đi tiếp ngay, không cần nhận tín hiệu cũ. Điều bảo đảm tính đúng đắn là **trạng thái bền trong `version` và việc kiểm tra dưới khóa**, không phải số lần phát tín hiệu.

Đây cũng là lý do không dùng một biến cục bộ kiểu `wasSignalled` bên ngoài cơ chế khóa để quyết định có chờ hay không. Kiểm tra dữ liệu, chờ và cập nhật phải tuân thủ cùng hợp đồng đồng bộ.

## 6. Chọn signal hay signalAll

Với ví dụ phiên bản, nhiều người có thể chờ các mức khác nhau: một người chờ phiên bản 1, người khác chờ phiên bản 5. Khi phiên bản lên 1, nếu chỉ đánh thức nhầm người chờ 5 thì nó lại ngủ, còn người chờ 1 có thể chưa được đánh thức. `signalAll()` cho mọi người kiểm tra điều kiện riêng của mình.

Không có quy tắc mọi chương trình đều phải dùng `signalAll()`. `signal()` có thể phù hợp khi các người chờ tương đương và mỗi lần thay đổi chỉ cho phép một người tiến tiếp, nhưng cần chứng minh không bỏ sót người đủ điều kiện. Nhiều nhóm điều kiện độc lập có thể dùng nhiều `Condition` tạo từ cùng khóa ghi, chẳng hạn `notEmpty` và `notFull`.

Đánh thức tất cả không cho phép tất cả cùng sở hữu ghi: họ vẫn lần lượt lấy khóa và kiểm tra lại. Không suy ra thứ tự hoàn tất tác vụ chỉ từ việc đã được phát tín hiệu.

## 7. Chờ có thời hạn và xử lý ngắt

`await()` có thể ném `InterruptedException`; phương thức nên truyền ngoại lệ lên khi đó là hợp đồng hủy phù hợp. Nếu xử lý ở ranh giới một tác vụ không thể ném tiếp, thường cần kết thúc công việc và khôi phục cờ bằng `Thread.currentThread().interrupt()`. Không bắt ngoại lệ rồi âm thầm tiếp tục chờ vô hạn.

Khi cần thời hạn, `awaitNanos()` trả số nano giây ước lượng còn lại. Giảm ngân sách chờ qua mỗi vòng lặp, thay vì cấp lại toàn bộ thời hạn sau mỗi lần thức dậy. Ví dụ dưới đây là một phương thức bổ sung vào `VersionedValue`; nó dùng các trường đã có:

```java
boolean awaitVersion(long expected, long timeoutNanos)
        throws InterruptedException {
    rw.writeLock().lockInterruptibly();
    try {
        long remaining = timeoutNanos;
        while (version < expected) {
            if (remaining <= 0L) {
                return false;
            }
            remaining = changed.awaitNanos(remaining);
        }
        return true;
    } finally {
        rw.writeLock().unlock();
    }
}
```

Thời hạn trong phương thức minh họa giới hạn phần chờ điều kiện **sau khi lấy được ghi**, không bao gồm toàn bộ thời gian chờ lấy khóa. Cũng không hứa phương thức trả về đúng một mốc thời gian cứng: nó còn phải lấy lại khóa trước khi kết thúc chờ. Nếu yêu cầu là một ngân sách cho toàn bộ thao tác, cần tính thời gian còn lại từ một mốc bắt đầu và áp dụng cả cho việc lấy khóa.

Các biến thể không nhận ngắt chỉ phù hợp khi chủ động chọn hợp đồng đó; không dùng để che việc thiết kế hủy tác vụ chưa rõ ràng.

## 8. Lỗi đặc biệt khi kết hợp khóa đọc và Condition

**Không gọi chờ trong khi vẫn giữ thêm khóa đọc trên cùng `ReentrantReadWriteLock`.** `await()` nhả khóa ghi nhưng không nhả các lần giữ đọc. Luồng cập nhật cần ghi có thể bị chặn bởi chính phần đọc còn lại của người đang chờ, khiến không ai làm điều kiện thành đúng. Đây là cảnh báo cụ thể của [WriteLock.newCondition](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.WriteLock.html#newCondition()).

Những lỗi khác cần tránh:

- Chỉ lấy đọc rồi gọi `await()` hoặc `signalAll()`: không sở hữu ghi, gây `IllegalMonitorStateException`.
- Giữ ghi của một đối tượng khóa nhưng dùng `Condition` tạo từ đối tượng khóa khác.
- Phát tín hiệu ngoài phạm vi giữ ghi hoặc quên cập nhật trạng thái trước khi báo.
- Thay `while` bằng `if`, bỏ qua việc trạng thái phải được kiểm tra lại.
- Gọi `changed.wait()` hoặc `changed.notifyAll()` để thay `await()`/`signalAll()`: đó là cơ chế monitor của đối tượng, không phải hàng đợi `Condition` đang dùng.
- Tưởng rằng tên hàm bắt đầu bằng `read` cho phép gọi chờ bằng khóa đọc.

Khi rà soát mã, hãy chỉ rõ ba thứ: **mệnh đề đang chờ, khóa bảo vệ mệnh đề đó, và những thay đổi dữ liệu nào phải phát tín hiệu**. Nếu thiếu một trong ba, chương trình dễ chờ mãi hoặc tiếp tục khi điều kiện chưa đúng.
