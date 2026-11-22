# Giới hạn nâng cấp từ khóa đọc sang khóa ghi

## 1. Vấn đề xuất hiện khi đang đọc nhưng phát hiện cần sửa

Một bộ nhớ đệm thường đọc dữ liệu trước. Nếu chưa có dữ liệu, luồng phải tải và lưu kết quả. Ý tưởng dễ nảy sinh là: giữ khóa đọc để kiểm tra, rồi lấy thêm khóa ghi ngay bên trong nhánh thiếu dữ liệu. Với `ReentrantReadWriteLock`, cách này không thực hiện được.

**Nâng cấp khóa (lock upgrading)** là chuyển từ chỉ giữ quyền đọc sang quyền ghi. `ReentrantReadWriteLock` không hỗ trợ nâng cấp trực tiếp trong khi luồng còn giữ khóa đọc. Giới hạn này vẫn áp dụng trên Java hiện hành; không phải hành vi cũ chỉ riêng Java 5. `ReadWriteLock` là giao diện, còn quy tắc chuyển đổi thuộc lớp triển khai cụ thể. Xem [ReadWriteLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReadWriteLock.html).

Bài này dùng `ReentrantReadWriteLock` và ví dụ Java 17+. Mục tiêu là hiểu điểm chờ, khoảng chuyển tiếp và cách kiểm tra lại dữ liệu.

## 2. Vì sao tái nhập không cho phép đọc → ghi?

Tái nhập cho phép một luồng lấy lại loại khóa mà nó đang giữ. Khóa đọc có thể được nhiều luồng giữ đồng thời; khóa ghi cần quyền độc quyền. Từ việc một luồng đã đọc được dữ liệu không thể suy ra rằng nó đang có quyền loại trừ mọi luồng đọc khác.

| Quyền luồng hiện tại đang giữ | Yêu cầu mới | Ý nghĩa |
| --- | --- | --- |
| Đọc | Đọc | Tái nhập đọc được hỗ trợ |
| Ghi | Ghi | Tái nhập ghi được hỗ trợ |
| Ghi | Đọc | Được hỗ trợ; có thể dùng để hạ khóa |
| Chỉ đọc | Ghi | Không nâng cấp trực tiếp được |

Trường hợp cuối vẫn thất bại **kể cả luồng hiện tại là luồng đọc duy nhất**. Nếu nó dùng `lock()` để chờ ghi mà không nhả đọc, nó không tự tiến đến được lệnh nhả đọc phía sau. Xem [hợp đồng ReentrantReadWriteLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html).

### Chu trình chờ tự gây ra

Giả sử T1 thực hiện:

```java
// Đoạn minh họa lỗi; không chạy vì có thể chờ vô hạn.
rw.readLock().lock();
try {
    rw.writeLock().lock(); // Không thể nâng cấp khi còn giữ đọc.
    try {
        updateData();
    } finally {
        rw.writeLock().unlock();
    }
} finally {
    rw.readLock().unlock(); // T1 chưa thể đi tới đây.
}
```

T1 chờ quyền ghi; quyền ghi chưa thể được cấp khi phần đọc của T1 vẫn tồn tại; phần đọc chỉ được nhả sau khi lời gọi chờ ghi kết thúc. Nếu cả T1 và T2 cùng giữ đọc rồi cùng chờ ghi, cả hai đều duy trì chướng ngại cho việc cấp quyền ghi.

Đây là lỗi thiết kế quyền truy cập. Thêm `try/finally` chỉ bảo đảm nhả khóa khi luồng thực thi tới đó, không khiến một lời gọi bị chặn tự kết thúc.

## 3. `tryLock()` và thời hạn chờ chỉ thay cách thất bại

Khi chỉ giữ đọc mà thử lấy ghi:

- `writeLock().tryLock()` trả `false` ngay.
- `writeLock().tryLock(timeout, unit)` có thể hết thời hạn rồi trả `false`; nó còn có thể ném `InterruptedException`.
- `writeLock().lock()` không cung cấp cơ chế hủy chờ bằng thời hạn.

Dùng thời hạn giúp chương trình có đường thoát, nhưng không tạo ra khả năng chuyển đổi khóa. Sau kết quả `false`, luồng vẫn giữ khóa đọc cho đến khi tự nhả nó. Chỉ được gọi `unlock()` ghi nếu việc lấy ghi thực sự thành công. Xem [các phương thức WriteLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.WriteLock.html).

Không sửa lỗi bằng cách lặp `tryLock()` trong khi vẫn giữ đọc: điều kiện ngăn cấp ghi vẫn còn ở mọi vòng lặp. Chính sách công bằng cũng không biến yêu cầu nâng cấp thành hợp lệ.

## 4. Quy trình đúng: nhả đọc, lấy ghi, kiểm tra lại

Nếu kết quả đọc cho thấy cần thay đổi, thực hiện theo thứ tự:

1. Ghi nhận rằng có thể cần cập nhật.
2. Kết thúc phạm vi đọc và nhả **tất cả lần giữ đọc của luồng hiện tại trên cùng khóa**.
3. Lấy khóa ghi.
4. Đọc lại trạng thái liên quan dưới khóa ghi.
5. Cập nhật chỉ khi điều kiện vẫn còn đúng.
6. Nhả khóa ghi trong `finally`.

Bước 2 → 3 có một khoảng chuyển tiếp: không còn khóa nào của luồng bảo vệ dữ liệu trong khoảng đó. Đây không phải phép chuyển đổi nguyên tử. Ví dụ:

| Thời điểm | T1 | T2 |
| --- | --- | --- |
| 1 | Đọc thấy bộ nhớ đệm trống | Đọc thấy bộ nhớ đệm trống |
| 2 | Nhả đọc | Nhả đọc |
| 3 | Lấy ghi, tải dữ liệu, nhả ghi | Chờ ghi |
| 4 | Đã hoàn tất | Lấy ghi, phải kiểm tra lại |

Nếu T2 tin vào kết quả đọc tại thời điểm 1, nó có thể tải dữ liệu lần nữa hoặc ghi đè kết quả T1. Dù hai lần ghi đã được khóa để không chạy đồng thời, quyết định cập nhật vẫn sai. **Loại trừ tương hỗ không thay thế tính đúng đắn của điều kiện cập nhật.**

## 5. Ví dụ đầy đủ: quan sát thất bại và tránh tải hai lần

Chương trình có hai phép thử:

- Luồng `main` giữ đọc rồi thử lấy ghi có thời hạn. Nó in `false` và nhả đọc.
- Hai tác vụ cùng thấy bộ nhớ đệm trống. `CountDownLatch` chỉ dùng để chủ động tạo tình huống này trong phép thử. Sau khi nhả đọc, cả hai xin ghi; nhờ kiểm tra lại dưới ghi, chỉ một tác vụ khởi tạo dữ liệu.

Lưu thành `UpgradeLimitDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.ReentrantReadWriteLock;

public class UpgradeLimitDemo {
    private static void demonstrateLimit() throws InterruptedException {
        ReentrantReadWriteLock rw = new ReentrantReadWriteLock();
        rw.readLock().lock();
        try {
            boolean acquired = rw.writeLock().tryLock(10, TimeUnit.MILLISECONDS);
            try {
                System.out.println("upgrade acquired=" + acquired);
                System.out.println("read holds=" + rw.getReadHoldCount());
            } finally {
                if (acquired) {
                    rw.writeLock().unlock();
                }
            }
        } finally {
            rw.readLock().unlock();
        }
    }

    private static final class Cache {
        private final ReentrantReadWriteLock rw = new ReentrantReadWriteLock();
        private String data;
        private int initializationCount;

        String get(CountDownLatch bothReadMiss) throws InterruptedException {
            rw.readLock().lock();
            try {
                if (data != null) {
                    return data;
                }
            } finally {
                rw.readLock().unlock();
            }

            // Chỉ phục vụ phép thử: chờ khi đã nhả khóa đọc.
            bothReadMiss.countDown();
            bothReadMiss.await();

            rw.writeLock().lockInterruptibly();
            try {
                if (data == null) {
                    data = "ready";
                    initializationCount++;
                }
                return data;
            } finally {
                rw.writeLock().unlock();
            }
        }

        int initializationCount() {
            rw.readLock().lock();
            try {
                return initializationCount;
            } finally {
                rw.readLock().unlock();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        demonstrateLimit();
        Cache cache = new Cache();
        CountDownLatch bothReadMiss = new CountDownLatch(2);
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            Future<String> first = pool.submit(() -> cache.get(bothReadMiss));
            Future<String> second = pool.submit(() -> cache.get(bothReadMiss));
            System.out.println("first=" + first.get());
            System.out.println("second=" + second.get());
            System.out.println("initializations=" + cache.initializationCount());
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Dùng JDK 17 trở lên:

```shell
javac -encoding UTF-8 UpgradeLimitDemo.java
java UpgradeLimitDemo
```

Stdout:

```text
upgrade acquired=false
read holds=1
first=ready
second=ready
initializations=1
```

Lần thử ghi thất bại không tiêu thụ lần giữ đọc nên `read holds=1`. Hai tác vụ đều đi qua nhánh thiếu dữ liệu trước khi thử ghi: tác vụ đầu không thể khởi tạo cho đến khi tác vụ còn lại đã gọi `countDown()`. Sau đó, tác vụ nào được quyền ghi trước sẽ khởi tạo; tác vụ còn lại chỉ đọc lại dữ liệu đã có. `first` là tên biến nhận tác vụ thứ nhất, không tuyên bố tác vụ đó chắc chắn lấy khóa ghi trước.

Giá trị trả về là `String` bất biến nên có thể dùng sau khi nhả khóa. Nếu thay bằng đối tượng có thể bị sửa, cần thiết kế riêng cách sao chép hoặc bảo vệ quyền truy cập sau khi trả về.

Trong mã ứng dụng, bỏ phần `CountDownLatch` phục vụ phép thử. Giữ nguyên hai lần kiểm tra `data`: lần dưới đọc cho đường đọc thông thường; lần dưới ghi quyết định có khởi tạo hay không. Không dùng `Thread.sleep()` để suy luận rằng một luồng khác đã tới một trạng thái khóa cụ thể.

## 6. Những điểm phải kiểm tra trong chuỗi gọi

### Một lần nhả có thể chưa đủ

Khóa đọc cho phép tái nhập. Nếu hàm cha đã giữ đọc, hàm con lấy thêm đọc rồi nhả một lần, phần đọc của hàm cha vẫn còn. Hàm con không thể tự ý chuyển sang ghi như ví dụ `Cache.get()` mà bỏ qua điều kiện này.

`getReadHoldCount()` cho biết số lần giữ đọc của luồng hiện tại. Nó hữu ích khi chẩn đoán, nhưng không nên dùng một vòng lặp nhả toàn bộ khóa của hàm cha: làm vậy phá hợp đồng bảo vệ dữ liệu của bên gọi. Hãy thiết kế ranh giới thao tác để quyết định đọc hay ghi được thực hiện ở nơi sở hữu toàn bộ phạm vi khóa. Xem [quy tắc giữ và nhả ReadLock](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.ReadLock.html).

### Nếu biết chắc phải cập nhật, lấy ghi từ đầu

Với một thao tác luôn sửa dữ liệu, có thể lấy khóa ghi ngay, kiểm tra và cập nhật trong cùng phạm vi. Cách này tránh khoảng chuyển tiếp đọc → ghi. Đổi lại, phần kiểm tra cũng nằm dưới quyền độc quyền; không còn lợi ích đọc đồng thời trong phạm vi đó. Chọn cách này theo ý nghĩa thao tác, không dựa vào việc tên phương thức có chứa chữ `get` hay `update`.

### Hạ khóa là chiều khác

Luồng đang giữ ghi có thể lấy thêm đọc rồi nhả hết ghi, tiếp tục đọc dưới quyền đọc. Khả năng hạ khóa này không kéo theo khả năng nâng khóa. Thứ tự nhả ghi rồi mới lấy đọc vẫn có khoảng trống cho người ghi khác chen vào.

## 7. Kiểm tra tính đúng đắn

Trước khi chấp nhận một luồng xử lý đọc rồi ghi, tự trả lời:

- Tại thời điểm xin ghi, luồng còn giữ bất kỳ lần đọc nào trên cùng khóa không?
- Trong khoảng nhả đọc và lấy ghi, dữ liệu có thể đã thay đổi thế nào?
- Điều kiện quyết định cập nhật đã được kiểm tra lại sau khi có quyền ghi chưa?
- Mọi đường trả về và ngoại lệ có nhả đúng khóa đã lấy thành công không?
- Tất cả truy cập dữ liệu có dùng cùng đối tượng khóa và cùng quy tắc đọc/ghi không?

Mẫu `lock(); try { ... } finally { unlock(); }` giúp quản lý vòng đời quyền giữ khóa. Nó vẫn cần một thuật toán chuyển trạng thái đúng. Xem [Lock và quản lý phạm vi khóa](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/locks/Lock.html).
