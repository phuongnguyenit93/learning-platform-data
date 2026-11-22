# Chính sách công bằng và nguy cơ chờ lâu

## 1. Đọc được cùng nhau chưa đủ để quyết định ai có lượt tiếp theo

Read-write lock cho phép nhiều reader cùng giữ khóa đọc, nhưng writer cần quyền độc quyền. Khi cả hai phía đều có người chờ, phải có một chính sách quyết định bên nào được vào.

Ví dụ:

```text
R1 đang đọc
W1 tới và chờ ghi
R2 tới sau, cũng muốn đọc
```

Nếu luôn nhận thêm reader mới, W1 có thể phải chờ rất lâu. Nếu luôn ưu tiên writer, các reader có thể bị trì hoãn khi writer liên tục tới.

**Công bằng (fairness)** là chính sách điều phối lượt xin khóa, không phải thay đổi việc read lock được chia sẻ còn write lock độc quyền.

Trong ReentrantReadWriteLock, có hai chế độ: không công bằng mặc định và công bằng khi truyền true vào constructor. Cả hai vẫn áp dụng trong Java hiện hành; ví dụ dùng Java 17+.

## 2. Cấu hình ở cùng một cặp khóa

```java
ReentrantReadWriteLock defaultGuard =
        new ReentrantReadWriteLock();

ReentrantReadWriteLock fairGuard =
        new ReentrantReadWriteLock(true);
```

Các khóa đọc và ghi lấy từ fairGuard cùng tuân theo chính sách của đối tượng ấy, với những ngoại lệ theo từng phương thức xin khóa.

Không phải read lock có một queue nghiệp vụ riêng còn write lock có queue không liên quan. Chúng phối hợp trên cùng một trạng thái đồng bộ.

`isFair()` cho biết chính sách đã chọn. Không có setter để đổi trực tiếp fairness của một đối tượng đang hoạt động.

Không thay khóa đang bảo vệ dữ liệu bằng một đối tượng mới chỉ để “bật fair” trong lúc các luồng còn dùng khóa cũ; khi đó hai nhóm có thể không còn bảo vệ cùng một vùng loại trừ.

## 3. Chế độ không công bằng: không có cam kết thứ tự tới trước

Constructor mặc định tương đương chọn chế độ không công bằng.

Đặc điểm cần hiểu:

- Thứ tự vào read/write lock không được cam kết theo lượt tới.
- Cơ chế có thể ưu tiên cơ hội thực thi để đạt thông lượng tốt hơn trong một số tải.
- Khi tranh chấp liên tục, một số reader hoặc writer có thể bị trì hoãn không xác định.
- Không có hợp đồng “reader luôn thắng” hoặc “writer luôn thắng” cho mọi lần xin khóa.

Không được diễn giải rằng dùng nonfair thì chắc chắn writer sẽ bị đói trong mọi chương trình. Nguy cơ phụ thuộc mẫu truy cập và lịch thực thi; một lần chạy thử không gặp vấn đề cũng không tạo bảo đảm thứ tự.

Tương tự, thấy một reader tới sau vào trước chưa đủ để tuyên bố có starvation. Starvation nói về việc một bên liên tục không được tiến triển, không phải chỉ một lần đảo thứ tự.

Hợp đồng chế độ được mô tả trong [ReentrantReadWriteLock API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html).

## 4. Chế độ công bằng: gần theo thứ tự chờ, có nhóm reader

Khi fair=true, các luồng tranh chấp theo chính sách gần với thứ tự tới chờ. Một writer chờ lâu nhất có thể được lượt ghi, hoặc một nhóm reader đã chờ trước các writer có thể cùng được lượt đọc.

Nó không biến read lock thành khóa độc quyền chỉ cho một reader tại một thời điểm.

Với reader mới không phải tái nhập, nếu có writer đang chờ trước theo chính sách, reader có thể phải đợi ngay cả khi một reader khác vẫn đang giữ read lock.

Quay lại ví dụ:

```text
R1 giữ read lock
W1 chờ write lock
R2 mới xin read lock theo đường tôn trọng fairness

R1 nhả -> W1 lấy và nhả -> R2 có cơ hội lấy
```

Sơ đồ diễn tả trường hợp đã có thứ tự chờ xác định, không phải suy ra thứ tự từ thời điểm log “bắt đầu phương thức” của các luồng.

### Thứ tự gọi không luôn là thứ tự xếp chờ

Một luồng có thể in log rồi bị tạm dừng trước khi tới đường xin khóa. Luồng khác in sau nhưng lại tới khóa trước.

Vì vậy, kiểm thử fairness không nên chỉ so hai dấu thời gian trước lời gọi lock rồi coi đó là bằng chứng thứ tự nội bộ.

## 5. Fair không phải cam kết thời hạn

Một writer đến lượt vẫn phải chờ các reader đang giữ khóa nhả. Nếu reader làm I/O rất lâu dưới read lock, fairness không tự ép reader thoát.

Những điều fair=true không cung cấp:

- Mỗi luồng được cùng thời lượng CPU.
- Mọi lời xin khóa thành công trong một số mili giây cố định.
- Tự sửa khóa quên unlock.
- Tự phá chu trình deadlock giữa nhiều tài nguyên.
- Tự nâng read lock thành write lock.
- Bảo đảm mọi kiểu xin khóa đều không vượt hàng.

Fairness của lock khác công bằng của bộ lập lịch hệ điều hành. Một luồng đã có quyền tiến lên vẫn cần được cấp thời gian chạy.

Nếu có yêu cầu thời hạn, xem xét `tryLock(timeout, unit)` và quy định phản hồi khi không lấy được khóa; đừng chỉ bật fair rồi tuyên bố đã có giới hạn độ trễ.

## 6. tryLock không thời hạn là ngoại lệ quan trọng

Với cả ReadLock và WriteLock của ReentrantReadWriteLock, lời:

```java
boolean acquired = lock.tryLock();
```

không tuân theo fairness giống đường chờ thông thường. Nó có thể lấy khóa nếu trạng thái cho phép tại lúc gọi, dù đã có luồng chờ trước.

Hành vi chen vào này thường được gọi là barging. Nó không vượt qua điều kiện loại trừ: reader vẫn không lấy được khi writer khác đang giữ write lock. Nó bỏ qua ràng buộc thứ tự chờ, không bỏ qua tính đúng của trạng thái khóa.

### Muốn thử ngay mà tôn trọng fairness

Có thể dùng overload có thời hạn bằng 0:

```java
boolean acquired =
        lock.tryLock(0, TimeUnit.SECONDS);
```

Đường này tôn trọng lựa chọn fairness theo hợp đồng của lớp và có thể báo InterruptedException. Nó không chờ một khoảng dương, nhưng khác tryLock() cả về chính sách lẫn phản hồi ngắt.

Không kết hợp:

```java
lock.tryLock() || lock.tryLock(timeout, unit)
```

rồi cho rằng toàn bộ biểu thức giữ fairness. Nhánh đầu vẫn cho phép chen vào.

Xem chi tiết [ReadLock.tryLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.ReadLock.html) và [WriteLock.tryLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.WriteLock.html).

## 7. Chương trình Java 17+: tryLock có thể vượt writer đang chờ

Thí nghiệm tạo một fair lock. Main giữ read lock để writer phải chờ; một luồng khác thử lấy read lock bằng hai overload.

Để dựng tình huống, chương trình quan sát writer đã vào hàng chờ trong khi main vẫn giữ read lock. Phương thức quan sát chỉ phục vụ thí nghiệm có điều kiện ổn định, không phải mẫu thuật toán đồng bộ nghiệp vụ.

Lưu thành **`ReadWriteFairnessDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.LockSupport;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class ReadWriteFairnessDemo {
    record Probe(boolean immediate, boolean fairTimed) {}

    public static void main(String[] args) throws Exception {
        ReentrantReadWriteLock guard =
                new ReentrantReadWriteLock(true);
        Lock read = guard.readLock();
        Lock write = guard.writeLock();

        ExecutorService pool = Executors.newFixedThreadPool(2);
        AtomicReference<Thread> writerThread =
                new AtomicReference<>();
        CountDownLatch writerRequested = new CountDownLatch(1);

        Future<Boolean> writer = null;

        try {
            read.lock();
            try {
                writer = pool.submit(() -> {
                    writerThread.set(Thread.currentThread());
                    writerRequested.countDown();

                    write.lockInterruptibly();
                    try {
                        return true;
                    } finally {
                        write.unlock();
                    }
                });

                if (!writerRequested.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "Writer did not request the lock");
                }

                waitForQueuedWriter(guard, writerThread.get());

                Future<Probe> probeFuture = pool.submit(() -> {
                    boolean immediate = read.tryLock();
                    if (immediate) {
                        read.unlock();
                    }

                    boolean fairTimed =
                            read.tryLock(0, TimeUnit.SECONDS);
                    if (fairTimed) {
                        read.unlock();
                    }

                    return new Probe(immediate, fairTimed);
                });

                Probe probe =
                        probeFuture.get(5, TimeUnit.SECONDS);

                System.out.println("fair: " + guard.isFair());
                System.out.println(
                        "read tryLock(): " + probe.immediate());
                System.out.println(
                        "read timed tryLock(0): "
                        + probe.fairTimed());
            } finally {
                read.unlock();
            }

            System.out.println(
                    "writer after release: "
                    + writer.get(5, TimeUnit.SECONDS));
        } finally {
            if (writer != null && !writer.isDone()) {
                writer.cancel(true);
            }

            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Executor did not terminate");
            }
        }
    }

    private static void waitForQueuedWriter(
            ReentrantReadWriteLock guard, Thread writer)
            throws InterruptedException {
        long started = System.nanoTime();
        long limit = TimeUnit.SECONDS.toNanos(5);

        while (!guard.hasQueuedThread(writer)) {
            if (Thread.currentThread().isInterrupted()) {
                throw new InterruptedException();
            }
            if (System.nanoTime() - started >= limit) {
                throw new IllegalStateException(
                        "Writer was not observed in the queue");
            }
            LockSupport.parkNanos(
                    TimeUnit.MILLISECONDS.toNanos(1));
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ReadWriteFairnessDemo.java
java ReadWriteFairnessDemo
```

Stdout chính xác:

```text
fair: true
read tryLock(): true
read timed tryLock(0): false
writer after release: true
```

### Vì sao hai lần thử khác nhau?

Main chưa nhả read lock nên writer không thể lấy write lock và rời hàng chờ trong giai đoạn probe. Luồng probe là reader mới, không phải main đang tái nhập.

TryLock không thời hạn cho reader mới cùng vào vì chưa có writer nắm khóa. Overload timed bằng 0 nhận biết writer đã chờ và không chen vào theo chính sách fair.

Sau khi main nhả khóa, writer mới được thực hiện phần của mình và hoàn tất.

Ví dụ không cố “chứng minh starvation” bằng một số vòng chạy hữu hạn. Nó xác minh một khác biệt có hợp đồng rõ giữa hai đường xin khóa.

### Giới hạn của phép quan sát

HasQueuedThread và các số đo tương tự được thiết kế cho giám sát. Ở đây chúng giúp dựng thí nghiệm khi main giữ trạng thái khiến writer không thể thành công trước lúc mở khóa.

Không sao chép thành quy tắc “thấy không có người chờ thì tự truy cập dữ liệu không cần khóa”. Trạng thái có thể đổi ngay sau lần đọc, và phép đo không tạo quyền sở hữu.

Các giới hạn năm giây giúp thử nghiệm báo lỗi khi thiếu tiến triển. Khoảng park nhỏ chỉ giảm quay bận khi quan sát; kết luận không dựa vào giả định writer chắc chắn xếp hàng sau một lần sleep cố định.

## 8. Tái nhập khác với người mới chen vào

Một luồng đã giữ read lock hoặc write lock có quy tắc tái nhập riêng. Fairness không được hiểu như bắt luồng ấy luôn xếp lại từ đầu cho mọi lần lấy lại cùng khóa.

Nếu thử nghiệm lấy read lock hai lần trên cùng luồng, nó có thể đang đo tái nhập thay vì hành vi của một reader mới. Vì vậy, ví dụ dùng luồng probe khác với main.

Không dùng fairness để xử lý việc nâng read lên write. Giữ read rồi chờ write vẫn là mẫu nguy hiểm vì quyền đọc đang giữ có thể cản chính yêu cầu ghi đó.

Công bằng điều phối các lời xin phù hợp; nó không làm một chuyển chế độ vốn không được hỗ trợ trở nên an toàn.

## 9. Vì sao vẫn có thể chờ lâu?

| Nguyên nhân | Bật fair có tự sửa không? |
|---|---|
| Reader hoặc writer giữ khóa trong lúc gọi mạng | Không |
| Nhánh lỗi quên unlock | Không |
| Chu trình lấy nhiều khóa theo thứ tự khác nhau | Không |
| Nhiều tryLock() không thời hạn cho phép chen vào | Không bảo đảm giữ fairness |
| Tải ghi liên tục, công việc ghi dài | Không tạo thêm năng lực xử lý |
| Luồng đến lượt nhưng không được CPU cấp thời gian | Không điều khiển lịch hệ điều hành |
| Giữ read rồi chờ nâng lên write | Không |

Một writer chờ lâu có thể do reader giữ quá lâu, không phải vì thứ tự không công bằng. Phải đo thời gian **chờ lấy khóa** và thời gian **giữ khóa** riêng.

Nếu một vùng đọc làm quá nhiều việc, rút ngắn nó hoặc chụp dữ liệu phù hợp rồi xử lý ngoài khóa có thể hiệu quả hơn đổi fairness. Nhưng bản chụp phải đáp ứng yêu cầu nhất quán và không để tham chiếu thay đổi được lọt ra ngoài.

## 10. Đánh đổi thông lượng và độ trễ

Nonfair thường có cơ hội thông lượng cao hơn trong một số tải, vì không luôn phải giữ thứ tự chờ. Fair có thể giúp giảm nguy cơ một phía bị bỏ lại dưới tranh chấp, nhưng có chi phí và không bảo đảm nhanh hơn.

Không chọn chỉ dựa trên tổng số thao tác mỗi giây. Một hệ thống có throughput cao nhưng writer phải đợi rất lâu có thể không đáp ứng yêu cầu cập nhật.

Khi đánh giá, nên tách:

- Tỷ lệ đọc và ghi.
- Thời gian giữ read/write lock.
- Phân bố thời gian chờ của mỗi phía.
- Mức tranh chấp khi tải tăng.
- Số lần timeout hoặc hủy việc xin khóa.
- Thông lượng cùng độ trễ ở các trường hợp chờ lâu.

Không lấy một lần chạy có vài luồng làm kết luận hiệu năng chung. Kết quả phụ thuộc phần cứng, dữ liệu và công việc trong vùng bảo vệ.

Giao diện ReadWriteLock cũng lưu ý phải đo đạc theo mẫu truy cập; xem [ReadWriteLock API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReadWriteLock.html).

## 11. Chọn chính sách và đường chờ có chủ đích

Một quy trình thực tế:

1. Xác định thao tác nào thật sự chỉ đọc, thao tác nào phải ghi.
2. Giữ vùng có khóa gọn và nhả bằng finally.
3. Kiểm tra có đường nào gọi tryLock không thời hạn hoặc tái nhập khiến giả định thứ tự thay đổi không.
4. Đo riêng độ trễ của reader và writer khi tranh chấp.
5. Chọn fair nếu yêu cầu thứ tự chờ và tính tiến triển của hai phía phù hợp với đánh đổi.
6. Dùng thời hạn hoặc ngắt tại nơi cần phản hồi hủy, cùng chính sách thất bại rõ.

Timed tryLock trả false chỉ nói lần xin ấy không thành công trong ngân sách; không tự là bằng chứng starvation. Một reader đang giữ khóa lâu hợp lệ cũng có thể khiến timeout.

Không thử lại ngay vô hạn bằng tryLock trong vòng rỗng để “tự tạo công bằng”. Việc đó vừa có thể cho phép chen vào vừa tiêu tốn CPU.

## 12. Tự kiểm tra

1. Nonfair có cam kết reader luôn được ưu tiên hơn writer không?
2. Fair=true có biến read lock thành chỉ cho một reader giữ không?
3. Vì sao một reader mới có thể chờ dù đang có reader khác giữ read lock?
4. TryLock không thời hạn có tuân theo fair như timed tryLock không?
5. Fair có bảo đảm lấy khóa trong 100 ms không?
6. Thấy một luồng được vào sau một lần timeout của luồng khác có đủ để chứng minh starvation không?

**Gợi ý:** (1) Không. (2) Không. (3) Chính sách có thể giữ lượt cho writer đã chờ trước. (4) Không. (5) Không. (6) Không; phải phân tích tiến triển và điều kiện tranh chấp.

Fairness giúp điều phối lượt xin khóa, nhưng **thời gian giữ khóa, cách dùng tryLock, tái nhập, khả năng được CPU thực thi và cấu trúc phụ thuộc** vẫn quyết định một luồng có phải chờ lâu hay không.
