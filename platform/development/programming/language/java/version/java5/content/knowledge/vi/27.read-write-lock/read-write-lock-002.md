# ReentrantReadWriteLock và khả năng đọc đồng thời

## 1. Khi nhiều người đọc không cần loại trừ nhau

Giả sử ứng dụng giữ một bảng cấu hình trong bộ nhớ. Nhiều luồng chỉ tra cứu cấu hình; thỉnh thoảng một luồng cập nhật toàn bộ một nhóm giá trị liên quan.

Dùng một khóa loại trừ thông thường làm mọi lần đọc phải lần lượt đi vào vùng bảo vệ, dù các lần đọc không thay đổi dữ liệu.

`ReentrantReadWriteLock` cung cấp hai chế độ phối hợp trên cùng một trạng thái khóa:

- **Khóa đọc (read lock)**: cho phép nhiều luồng đọc đồng thời khi không bị khóa ghi loại trừ.
- **Khóa ghi (write lock)**: dành quyền cập nhật độc quyền, loại trừ các reader khác và writer khác.

Điểm quan trọng không phải có hai đối tượng Lock bất kỳ, mà là chúng là **một cặp liên kết của cùng ReentrantReadWriteLock**.

Các ví dụ dùng Java 17+; cơ chế này vẫn áp dụng trong Java hiện hành.

## 2. ReadWriteLock và ReentrantReadWriteLock

`ReadWriteLock` là giao diện cung cấp `readLock()` và `writeLock()`. `ReentrantReadWriteLock` là một triển khai có khả năng lấy lại khóa bởi cùng luồng và có lựa chọn chính sách công bằng.

Ví dụ khai báo:

```java
ReentrantReadWriteLock guard = new ReentrantReadWriteLock();
Lock read = guard.readLock();
Lock write = guard.writeLock();
```

Các lớp thuộc `java.util.concurrent.locks`.

Không tạo một ReentrantReadWriteLock riêng trong mỗi phương thức hoặc mỗi lần gọi. Những luồng truy cập cùng dữ liệu phải dùng chung cặp khóa bảo vệ dữ liệu đó.

Giao diện và yêu cầu đồng bộ bộ nhớ được mô tả tại [ReadWriteLock API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReadWriteLock.html).

## 3. Bảng tương thích: ai được cùng giữ khóa?

Xét các luồng khác nhau truy cập cùng cặp khóa:

| Đang được giữ | Luồng khác muốn đọc | Luồng khác muốn ghi |
|---|---|---|
| Không ai giữ | Có thể lấy khóa theo chính sách | Có thể lấy khóa theo chính sách |
| Có reader, không có writer | Có thể cùng đọc, tùy chính sách chờ | Phải đợi reader nhả |
| Có writer | Phải đợi writer nhả | Phải đợi writer nhả |

“Tùy chính sách” có nghĩa một reader mới không nhất thiết được vào ngay chỉ vì hiện có reader khác. Chẳng hạn chế độ công bằng có thể yêu cầu reader mới chờ một writer đã xếp trước.

Bảng áp dụng cho những luồng khác nhau; luồng đang giữ khóa có quy tắc tái nhập riêng được giải thích ở phần sau.

### Đọc đồng thời là gì?

Hai reader có thể cùng giữ quyền đọc trong một khoảng thời gian. Điều đó không hứa rằng CPU chạy hai câu lệnh tại chính xác cùng nano giây.

Khả năng cùng đi vào vùng đọc giúp khai thác song song trên nhiều lõi khi công việc đủ lớn và dữ liệu phù hợp. Trên một lõi, các luồng có thể vẫn được luân phiên thực hiện.

## 4. Khóa đọc không biến lệnh ghi thành an toàn

Trong vùng đọc, ứng dụng phải giữ cam kết **không làm thay đổi trạng thái được cặp khóa bảo vệ**.

Ví dụ sai:

```java
read.lock();
try {
    hits++;
} finally {
    read.unlock();
}
```

Nếu nhiều luồng cùng làm vậy, chúng cùng giữ read lock và vẫn có thể ghi đè kết quả tăng của nhau. Read lock không loại trừ các reader.

Tên phương thức cũng không đủ để phân loại. Một phương thức có tên `get` nhưng cập nhật bộ nhớ đệm lười, tăng một trường thống kê hoặc làm thay đổi cấu trúc dữ liệu vẫn có thao tác ghi cần được thiết kế riêng.

Nếu thống kê dùng AtomicLong độc lập thì có thể có giao thức khác cho trường ấy, nhưng phải giải thích rõ nó không còn dựa vào quyền đọc để bảo vệ phép tăng.

### Toàn bộ đường ghi phải theo giao thức

Nếu writer cập nhật dưới write lock còn một nơi khác ghi trực tiếp không khóa, bảo đảm bị phá vỡ.

Tương tự, dùng read lock để đọc nhưng dùng `synchronized` trên một đối tượng không liên quan để ghi không tự tạo thành cùng một giao thức loại trừ. Mọi luồng phải thống nhất cách bảo vệ trạng thái.

## 5. Khuôn lấy và nhả khóa

Đoạn đọc:

```java
read.lock();
try {
    return settings.get(key);
} finally {
    read.unlock();
}
```

Đoạn ghi:

```java
write.lock();
try {
    settings.put(key, value);
} finally {
    write.unlock();
}
```

Đây là các đoạn minh họa trong phương thức của một lớp; settings, key và value do ứng dụng định nghĩa.

Đặt thao tác lock trước khối try bảo vệ vùng đã lấy khóa, rồi unlock trong finally. Nếu code trong vùng ném ngoại lệ, khóa vẫn được nhả.

Lock phải được nhả bởi luồng có quyền sở hữu tương ứng. Nếu lấy lại khóa nhiều lần, phải nhả đủ số lần; một lần unlock không xóa toàn bộ các lần giữ.

Các khuôn quản lý và khả năng xin khóa theo thời hạn/ngắt được mô tả tại [Lock API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/Lock.html).

### Khi cần phản hồi ngắt trong lúc xin khóa

Cả read lock và write lock của ReentrantReadWriteLock hỗ trợ `lockInterruptibly()`. Nếu xin khóa có thể bị ngắt, chỉ thực hiện unlock sau khi đã lấy thành công.

Với `tryLock`, chỉ nhả khi kết quả là true. Không đặt unlock trong một finally bao cả lần xin khóa thất bại.

## 6. Khả năng thấy dữ liệu mới không chỉ là tránh ghi cùng lúc

Cặp khóa còn có ý nghĩa đồng bộ bộ nhớ. Sau khi writer cập nhật dữ liệu rồi nhả write lock, một reader lấy read lock thành công theo giao thức tương ứng thấy các cập nhật đã được công bố qua lần nhả khóa đó.

Không cần biến mọi trường thành volatile chỉ để sao chép cùng vai trò công bố khi toàn bộ truy cập đã được bảo vệ đúng. Nhưng bỏ khóa ở một vài đường đọc hoặc để dữ liệu lọt ra ngoài vẫn có thể tạo vấn đề.

### Đừng trả tham chiếu thay đổi được rồi nghĩ vẫn được bảo vệ

Ví dụ một phương thức lấy read lock, trả về List nội bộ, sau đó nhả khóa. Nơi gọi giữ List và tự sửa nó ở ngoài vùng khóa đã vượt khỏi giao thức.

Các lựa chọn tùy mục đích:

- Trả một giá trị bất biến.
- Trả bản chụp có đủ mức sao chép cần thiết.
- Giữ thao tác trên cấu trúc nội bộ trong phương thức được bảo vệ.

Một bản sao danh sách chỉ sao chép cấu trúc danh sách không tự làm các phần tử bên trong bất biến. Phải xét cả dữ liệu được lồng bên trong kết quả.

## 7. Thí nghiệm Java 17+: hai reader cùng vào, writer phải đợi

Ví dụ giữ hai reader ở chốt sau khi chúng đã lấy read lock. Trong lúc đó, writer yêu cầu quyền ghi nhưng không thể vào vùng cập nhật.

Lưu thành **`ConcurrentReadersDemo.java`**:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.Lock;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class ConcurrentReadersDemo {
    public static void main(String[] args) throws Exception {
        ReentrantReadWriteLock guard =
                new ReentrantReadWriteLock();
        Lock read = guard.readLock();
        Lock write = guard.writeLock();

        int[] value = {5};
        CountDownLatch readersInside = new CountDownLatch(2);
        CountDownLatch releaseReaders = new CountDownLatch(1);
        CountDownLatch writerAttempting = new CountDownLatch(1);
        CountDownLatch writerInside = new CountDownLatch(1);

        ExecutorService pool = Executors.newFixedThreadPool(3);

        Callable<Integer> reader = () -> {
            read.lockInterruptibly();
            try {
                int observed = value[0];
                readersInside.countDown();
                releaseReaders.await();
                return observed;
            } finally {
                read.unlock();
            }
        };

        try {
            Future<Integer> first = pool.submit(reader);
            Future<Integer> second = pool.submit(reader);

            if (!readersInside.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Both readers did not enter");
            }

            System.out.println(
                    "read holds: " + guard.getReadLockCount());

            Future<?> writer = pool.submit(() -> {
                writerAttempting.countDown();
                write.lockInterruptibly();
                try {
                    writerInside.countDown();
                    value[0] = 99;
                } finally {
                    write.unlock();
                }
                return null;
            });

            if (!writerAttempting.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Writer did not request the lock");
            }

            boolean enteredBeforeRelease =
                    writerInside.await(20, TimeUnit.MILLISECONDS);
            System.out.println(
                    "writer before reader release: "
                    + enteredBeforeRelease);

            releaseReaders.countDown();

            System.out.println(
                    "reader 1: " + first.get(5, TimeUnit.SECONDS));
            System.out.println(
                    "reader 2: " + second.get(5, TimeUnit.SECONDS));

            writer.get(5, TimeUnit.SECONDS);

            read.lock();
            try {
                System.out.println("final value: " + value[0]);
            } finally {
                read.unlock();
            }
        } finally {
            releaseReaders.countDown();
            pool.shutdown();
            try {
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                    if (!pool.awaitTermination(
                            5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "Executor did not terminate");
                    }
                }
            } catch (InterruptedException e) {
                pool.shutdownNow();
                Thread.currentThread().interrupt();
                throw e;
            }
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 ConcurrentReadersDemo.java
java ConcurrentReadersDemo
```

Stdout chính xác:

```text
read holds: 2
writer before reader release: false
reader 1: 5
reader 2: 5
final value: 99
```

### Điều gì làm kết quả xác định?

Chốt readersInside chỉ mở sau khi cả hai reader đã lấy khóa. Chúng chưa nhả khóa trước khi main mở releaseReaders. Vì thế số lượt giữ read lock là 2 và writer không thể đi vào trước lúc đó.

Khoảng 20 ms là cửa sổ quan sát khi hai reader vẫn bị giữ; nó không được dùng để đoán reader đã bắt đầu. Việc có hai reader trong vùng được xác nhận bằng chốt.

Mỗi reader chụp giá trị 5 trước khi cho biết đã vào trong vùng. Writer phải đợi cả hai nhả read lock rồi mới đổi thành 99. Main đọc giá trị cuối dưới read lock sau khi đã nhận kết quả writer.

Phép đo getReadLockCount chỉ phục vụ minh họa. Trong ứng dụng chạy tự do, không lấy số đo rồi quyết định “không có reader nên tự ghi không cần khóa”; trạng thái có thể đổi giữa lúc kiểm tra và lúc dùng.

Main khai báo throws Exception để tập trung vào cơ chế. Các lời chờ năm giây giúp phát hiện thiếu tiến triển; ứng dụng thực cần xử lý ngắt và thất bại theo chính sách của nó.

## 8. Tái nhập và chuyển chế độ cần hiểu đúng

ReentrantReadWriteLock cho phép cùng luồng lấy lại chế độ khóa mà nó đang nắm theo quy tắc của lớp. Điều này hữu ích khi một phương thức đã giữ khóa gọi phương thức khác cũng xin khóa tương ứng.

Writer có thể lấy read lock khi đang giữ write lock. Có thể dùng điều này để hạ từ ghi xuống đọc: lấy read trước, sau đó nhả write, rồi tiếp tục đọc.

Ngược lại, **giữ read lock rồi chờ write lock không phải cách nâng cấp được hỗ trợ**. Writer cần hết lượt đọc đang cản nó, trong khi chính luồng xin ghi vẫn giữ một lượt đọc. Đường xin ghi có thể không tiến triển.

Nếu cần từ đọc chuyển sang ghi, thường phải nhả read, lấy write rồi kiểm tra lại điều kiện, vì một writer khác có thể đã cập nhật trong khoảng chuyển. Không dựa vào kết quả đọc cũ để ghi mà không kiểm tra lại.

Các quy tắc tái nhập, hạ chế độ và giới hạn nâng cấp nằm trong [ReentrantReadWriteLock API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html).

## 9. Nhiều reader không có nghĩa writer luôn có lượt nhanh

Constructor không đối số dùng chế độ không công bằng. Thứ tự vào khóa không được cam kết theo thứ tự tới; dưới tranh chấp kéo dài, một số reader hoặc writer có thể bị trì hoãn lâu.

Có thể chọn chế độ công bằng:

```java
ReentrantReadWriteLock guard =
        new ReentrantReadWriteLock(true);
```

Chế độ này dùng thứ tự gần theo thời điểm chờ và cho phép nhóm reader phù hợp vào cùng nhau. Nó không có nghĩa mọi luồng được một lát thời gian thực thi bằng nhau hoặc writer luôn nhanh hơn.

Reader mới ở chế độ công bằng có thể phải đợi writer đã chờ trước, nên không phải cứ đang có một reader là mọi reader mới đều được vào.

Các lời `tryLock()` không thời hạn của read/write lock không tuân theo lựa chọn fairness theo cùng cách chờ thông thường; không dùng chúng để chứng minh ứng dụng luôn giữ thứ tự công bằng.

Chọn fairness dựa trên yêu cầu độ trễ và đo tải thực. Chế độ công bằng có thể giảm thông lượng; chế độ mặc định cũng không phải bảo đảm một phía luôn bị đói.

## 10. Khi khóa đọc-ghi có ích và khi không

| Mẫu truy cập | Điều cần cân nhắc |
|---|---|
| Nhiều lần đọc tương đối dài, ghi ít | Có cơ hội hưởng lợi từ reader đồng thời |
| Đọc cực ngắn | Chi phí quản lý read-write lock có thể lớn hơn lợi ích |
| Ghi thường xuyên | Nhiều thời gian vẫn phải độc quyền; lợi ích đọc chung giảm |
| Có thể công bố bản chụp bất biến | Có thể không cần giữ read lock trong mỗi lần sử dụng |
| Chỉ cần thao tác độc lập trên một concurrent collection | Xem API collection trước khi bọc thêm khóa |
| Nhiều cấu trúc phải thay đổi cùng một bất biến | Cần một giao thức bao trùm toàn bộ thay đổi |

Không lựa chọn chỉ vì đếm “90% lời gọi là đọc”. Còn phải xét thời gian từng vùng, số luồng tranh chấp và chi phí sao chép hoặc đồng bộ.

Khóa đọc-ghi không tự phân vùng dữ liệu. Một write lock chung cho cả kho cấu hình vẫn làm mọi reader của kho ấy phải đợi lúc cập nhật. Nếu cần chia nhỏ, phải xác định lại bất biến và thứ tự lấy các khóa, tránh tạo chu trình khóa mới.

### Không giữ khóa lâu khi chờ bên ngoài

Một reader giữ khóa trong lúc chờ mạng vẫn ngăn writer cập nhật dù reader không đang dùng CPU. Một writer giữ khóa trong lúc làm I/O có thể làm toàn bộ reader ngừng tiến triển.

Nếu có thể, lấy một bản chụp phù hợp dưới read lock rồi nhả trước khi thực hiện phần chậm. Điều này chỉ đúng khi bản chụp đáp ứng yêu cầu nhất quán và không còn tham chiếu thay đổi được cần bảo vệ.

Trong thí nghiệm, chờ chốt dưới khóa là có chủ đích để nhìn thấy cơ chế, không phải khuyến nghị cho mã nghiệp vụ.

## 11. Những lỗi thường gặp

- Dùng read lock cho một phép tăng, thêm, xóa hoặc khởi tạo lười.
- Tạo một khóa mới mỗi lần gọi nên các luồng không thực sự phối hợp.
- Chỉ khóa thao tác ghi mà đọc trực tiếp ở nơi khác.
- Quên unlock khi phương thức có nhiều return hoặc ném ngoại lệ.
- Nhả khóa từ luồng khác với nơi đã lấy.
- Trả cấu trúc nội bộ ra ngoài rồi cho phép nơi gọi sửa không khóa.
- Giữ read rồi xin write, tưởng reentrant nghĩa mọi chuyển chế độ đều được.
- Dùng getReadLockCount hoặc isWriteLocked để thay cho thao tác xin khóa.
- Cho rằng nhiều reader cùng giữ read lock đồng nghĩa hiệu năng chắc chắn tăng.
- Cho rằng Condition được hỗ trợ trên read lock; chế độ đọc không hỗ trợ newCondition theo hợp đồng của lớp.

Những phương thức quan sát trạng thái phù hợp cho giám sát hoặc chẩn đoán. Chúng không tạo một thao tác kiểm tra-rồi-thực hiện nguyên tử cho dữ liệu nghiệp vụ.

## 12. Tự kiểm tra

1. Hai luồng cùng giữ read lock có thể cùng tăng một biến thường mà không mất cập nhật không?
2. Writer đang giữ write lock thì một reader ở luồng khác có được vào không?
3. Core của giao thức là hai Lock bất kỳ hay cặp khóa từ cùng một ReadWriteLock?
4. Vì sao trả List nội bộ sau khi nhả read lock có thể làm mất bảo vệ?
5. Một luồng giữ read lock rồi gọi write.lock có phải cách nâng cấp an toàn không?
6. Dữ liệu đọc rất ngắn và ghi thường xuyên có chắc nhanh hơn với khóa đọc-ghi không?

**Gợi ý:** (1) Không. (2) Không. (3) Cặp liên kết từ cùng khóa. (4) Nơi gọi có thể dùng hoặc sửa dữ liệu ngoài vùng bảo vệ. (5) Không. (6) Không; phải đo và xét mẫu truy cập.

Khả năng đọc đồng thời chỉ an toàn khi các reader thực sự chỉ đọc, các writer dùng quyền ghi độc quyền và mọi đường truy cập tuân theo cùng một giao thức bảo vệ dữ liệu.
