# Semaphore và số giấy phép truy cập tài nguyên

## 1. Từ tài nguyên hữu hạn đến giấy phép

Giả sử một bộ xử lý chỉ có thể phục vụ tối đa ba công việc cùng lúc. Hệ thống có thể có nhiều tác vụ, nhưng không nên để tất cả cùng vào vùng sử dụng bộ xử lý đó.

`Semaphore` biểu diễn quyền truy cập bằng một bộ đếm **giấy phép (permit)**:

- Muốn vào vùng giới hạn, lấy giấy phép.
- Hết giấy phép, đợi hoặc từ chối yêu cầu theo chính sách.
- Rời vùng giới hạn, trả giấy phép để bên khác có thể vào.

```text
Nhiều tác vụ -> lấy giấy phép -> dùng tài nguyên -> trả giấy phép
                    |
             chưa có giấy phép
                    |
                 chờ / bỏ cuộc
```

`Semaphore` xuất hiện từ Java 5 và vẫn phù hợp trong Java hiện đại. Bài dùng Java 17+ để minh họa.

Giấy phép không phải một đối tượng kết nối hay một “vé” Java được trả về. Semaphore lưu số đếm; ứng dụng tự liên kết quyền truy cập với tài nguyên cần bảo vệ.

## 2. Bộ đếm thay đổi như thế nào?

Với giới hạn hai lượt truy cập đồng thời:

```java
Semaphore slots = new Semaphore(2);
```

Đoạn minh họa cần import `java.util.concurrent.Semaphore`.

Nếu mỗi lượt lấy một giấy phép và trả đúng một giấy phép:

| Sự kiện | Giấy phép khả dụng | Số lượt đang giữ giấy phép |
| --- | --- | --- |
| Khởi tạo | 2 | 0 |
| A lấy thành công | 1 | 1 |
| B lấy thành công | 0 | 2 |
| C yêu cầu lấy | 0; C phải chờ | 2 |
| A trả, C nhận được giấy phép | 0 | 2 |
| B trả | 1 | 1 |
| C trả | 2 | 0 |

Công thức giúp hiểu giao thức giới hạn thông thường là:

```text
giấy phép khả dụng + giấy phép đang được giữ = sức chứa đã cấu hình
```

Công thức này chỉ đúng khi ứng dụng không tự tăng sức chứa, không làm rò rỉ và không trả thừa giấy phép. Semaphore không tự ghi nhớ một giới hạn tối đa cố định bằng tham số constructor: gọi `release()` sai vẫn có thể làm số đếm vượt giá trị khởi tạo.

Số giấy phép cũng không nhất thiết bằng số luồng. Một luồng có thể yêu cầu nhiều giấy phép cho một thao tác; nhiều tác vụ có thể đang chờ mà chưa giữ giấy phép nào.

## 3. Các thao tác chính

| Phương thức | Ý nghĩa |
| --- | --- |
| `acquire()` | Đợi nếu cần rồi lấy một giấy phép; có thể bị ngắt |
| `tryAcquire()` | Thử ngay; trả true nếu lấy được, false nếu không |
| `tryAcquire(timeout, unit)` | Đợi có thời hạn; trả false nếu hết hạn mà chưa lấy được |
| `release()` | Trả/thêm một giấy phép, có thể cho một bên đang chờ tiến triển |
| `acquire(n)` | Đợi đến khi lấy được cả n giấy phép theo yêu cầu |
| `release(n)` | Trả/thêm n giấy phép |
| `availablePermits()` | Quan sát số giấy phép hiện khả dụng |

Các phương thức quan sát không phải thao tác đặt chỗ. Đoạn sau có lỗi kiểm tra rồi hành động:

```java
// Sai: số đếm có thể đổi ngay sau lần kiểm tra.
if (slots.availablePermits() > 0) {
    useResource();
}
```

`useResource()` ở đây chỉ là tên minh họa cho công việc ứng dụng, không phải API của Java. Cần dùng `tryAcquire()` để việc kiểm tra và lấy quyền truy cập diễn ra theo một thao tác đúng:

```java
if (slots.tryAcquire()) {
    try {
        useResource();
    } finally {
        slots.release();
    }
} else {
    rejectOrRetryLater();
}
```

Hai hàm nghiệp vụ trong đoạn này là minh họa, chưa phải chương trình độc lập. Nhánh không lấy được giấy phép phải có chính sách rõ: từ chối, trả trạng thái bận, xếp hàng có giới hạn hoặc thử lại sau.

Hợp đồng chi tiết nằm trong [Semaphore](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Semaphore.html).

## 4. Mẫu lấy–trả đúng khi có ngoại lệ và ngắt luồng

Mẫu nền tảng cho một lượt dùng tài nguyên:

```java
slots.acquire();
try {
    useResource();
} finally {
    slots.release();
}
```

`acquire()` nằm trước khối `try/finally` trả giấy phép. Nếu việc lấy bị ngắt và ném `InterruptedException`, không có giấy phép nào được cấp cho lượt đó, nên không được trả.

Mẫu sai:

```java
// Sai: nếu acquire bị ngắt, finally vẫn trả một giấy phép chưa lấy.
try {
    slots.acquire();
    useResource();
} finally {
    slots.release();
}
```

Đối với biến thể có thời hạn:

```java
boolean acquired = slots.tryAcquire(200, TimeUnit.MILLISECONDS);
if (!acquired) {
    return;
}
try {
    useResource();
} finally {
    slots.release();
}
```

Đoạn minh họa cần import `TimeUnit`, có phương thức bao ngoài phù hợp với `return`, và xử lý/truyền tiếp `InterruptedException`. Giá trị 200 ms chỉ minh họa chính sách chờ; phải chọn thời hạn theo yêu cầu hệ thống.

Nếu tác vụ bị ngắt **sau khi đã lấy được** giấy phép và rời vùng dùng tài nguyên bằng ngoại lệ, `finally` vẫn trả giấy phép. Nếu tác vụ không hợp tác dừng và chưa rời vùng đó, giấy phép vẫn phải được giữ: việc luồng điều phối hết kiên nhẫn không chứng minh tài nguyên đã hết được sử dụng.

Khi bắt `InterruptedException` ở nơi không thể truyền tiếp, thường cần khôi phục cờ ngắt bằng `Thread.currentThread().interrupt()` rồi đi theo nhánh hủy/kết thúc phù hợp. Không tiếp tục như đã lấy được giấy phép khi lệnh lấy thực tế thất bại.

## 5. Thí nghiệm kiểm chứng tối đa hai tác vụ cùng vào

Chương trình có bốn tác vụ, executor bốn luồng, nhưng chỉ hai giấy phép. Một latch giữ hai tác vụ đầu ở trong vùng truy cập để main quan sát chắc chắn mức sử dụng bằng 2. Sau đó main mở cổng để mọi việc hoàn tất.

Lưu thành `SemaphoreResourceDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.Semaphore;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class SemaphoreResourceDemo {
    public static void main(String[] args) throws Exception {
        Semaphore slots = new Semaphore(2);
        CountDownLatch firstTwoInside = new CountDownLatch(2);
        CountDownLatch allowFinish = new CountDownLatch(1);
        AtomicInteger active = new AtomicInteger();
        AtomicInteger peak = new AtomicInteger();

        ExecutorService pool = Executors.newFixedThreadPool(4);
        List<Future<Integer>> futures = new ArrayList<>();

        try {
            for (int i = 1; i <= 4; i++) {
                final int value = i;
                futures.add(pool.submit(() -> {
                    slots.acquire();
                    try {
                        int current = active.incrementAndGet();
                        try {
                            peak.accumulateAndGet(current, Math::max);
                            firstTwoInside.countDown();
                            allowFinish.await();
                            return value * 10;
                        } finally {
                            active.decrementAndGet();
                        }
                    } finally {
                        slots.release();
                    }
                }));
            }

            if (!firstTwoInside.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("workers did not enter");
            }

            System.out.println("Active while held: " + active.get());
            allowFinish.countDown();

            int sum = 0;
            for (Future<Integer> future : futures) {
                sum += future.get(10, TimeUnit.SECONDS);
            }

            System.out.println("Peak active: " + peak.get());
            System.out.println("Sum: " + sum);
            System.out.println("Active after completion: " + active.get());
            System.out.println("Permits after completion: "
                    + slots.availablePermits());
        } finally {
            allowFinish.countDown();
            pool.shutdownNow();
        }
    }
}
```

Chạy:

```shell
javac SemaphoreResourceDemo.java
java SemaphoreResourceDemo
```

Stdout khi các tác vụ chạy bình thường trong thời hạn:

```text
Active while held: 2
Peak active: 2
Sum: 100
Active after completion: 0
Permits after completion: 2
```

Hai latch chỉ phục vụ thí nghiệm:

- `firstTwoInside` giúp main biết hai lượt truy cập đã thật sự bắt đầu.
- `allowFinish` ngăn hai lượt đó kết thúc trước khi main quan sát.

Chính semaphore giới hạn số bên vào, không phải latch. `AtomicInteger` chỉ đo số bên đang ở trong vùng và đỉnh quan sát được. Trong ứng dụng thực tế, thay phần chờ thí nghiệm bằng công việc sử dụng tài nguyên.

`Future.get()` làm nhiệm vụ đợi kết quả và nhận lỗi tác vụ. Việc semaphore có lại đủ giấy phép không phải cơ chế đợi tất cả công việc đã được gửi.

Các thời hạn 10 giây giúp thí nghiệm không chờ vô hạn ở những điểm nêu trên; không phải tham số chung cho mọi tài nguyên sản xuất.

## 6. Thí nghiệm ngắt khi chưa được cấp giấy phép

Lưu thành `SemaphoreInterruptDemo.java`:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Semaphore;
import java.util.concurrent.atomic.AtomicBoolean;

public class SemaphoreInterruptDemo {
    public static void main(String[] args) throws InterruptedException {
        Semaphore slots = new Semaphore(0);
        CountDownLatch ready = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean();

        Thread worker = new Thread(() -> {
            ready.countDown();
            try {
                slots.acquire();
                try {
                    throw new AssertionError("unexpected permit");
                } finally {
                    slots.release();
                }
            } catch (InterruptedException e) {
                interrupted.set(true);
                Thread.currentThread().interrupt();
            }
        });

        worker.start();
        ready.await();
        worker.interrupt();
        worker.join();

        System.out.println("Interrupted while acquiring: "
                + interrupted.get());
        System.out.println("Permits: " + slots.availablePermits());
    }
}
```

Chạy:

```shell
javac SemaphoreInterruptDemo.java
java SemaphoreInterruptDemo
```

Stdout:

```text
Interrupted while acquiring: true
Permits: 0
```

Semaphore khởi tạo 0 và không có ai cấp thêm giấy phép. Lệnh ngắt có thể đến ngay trước hoặc trong khi worker chờ `acquire()`; cả hai đều đi theo nhánh `InterruptedException` trong thí nghiệm bình thường này. Vì chưa lấy thành công, worker không chạy khối trả giấy phép; số đếm vẫn bằng 0.

Khởi tạo 0 là hợp lệ. Nó cũng có thể dùng cho một giao thức truyền tín hiệu chuyên biệt, nhưng cần phân biệt với mô hình giới hạn sức chứa thông thường.

## 7. Giấy phép không mang quyền sở hữu luồng

Semaphore không ghi nhận “giấy phép này thuộc luồng A”. Luồng B có thể gọi `release()` dù A là bên đã gọi `acquire()`.

Đặc điểm này hữu ích khi giao thức chủ động bàn giao quyền truy cập giữa các bên, nhưng cũng khiến lỗi trả thừa khó bị phát hiện tự động.

| Đặc điểm | Semaphore | ReentrantLock |
| --- | --- | --- |
| Quyền sở hữu theo luồng | Không | Có |
| Nhiều bên cùng giữ quyền | Có nếu đủ giấy phép | Một bên giữ khóa tại một thời điểm |
| Lấy lại từ cùng luồng | Vẫn cần thêm giấy phép | Hỗ trợ vào lại theo số lần giữ |
| Mục tiêu điển hình | Giới hạn sức chứa/đồng bộ bằng giấy phép | Bảo vệ vùng trạng thái cần loại trừ lẫn nhau |

Một semaphore có một giấy phép có thể tạo loại trừ lẫn nhau **nếu giao thức giữ số giấy phép không vượt 1**. Nó không tự trở thành một khóa có sở hữu hoặc có khả năng vào lại. Một luồng đang giữ giấy phép duy nhất mà gọi `acquire()` lần nữa có thể tự chờ mãi nếu không ai trả giấy phép.

Với nhu cầu khóa bảo vệ trạng thái thông thường, `synchronized` hoặc [ReentrantLock](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/locks/ReentrantLock.html) thường biểu đạt ý định rõ hơn.

## 8. Semaphore không tự chọn tài nguyên thật trong pool

Giả sử có ba kết nối. Lấy được một giấy phép chỉ cho biết ứng dụng được phép sử dụng một đơn vị sức chứa. Nó chưa chỉ ra kết nối nào đang rảnh.

Nếu các tác vụ cùng tìm và đánh dấu một kết nối trong một danh sách không có bảo vệ, chúng vẫn có thể lấy trùng một kết nối. Cần một cấu trúc/giao thức chọn–trả tài nguyên an toàn.

Đôi khi [BlockingQueue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/BlockingQueue.html) chứa các tài nguyên rảnh diễn đạt trực tiếp hơn: lấy một đối tượng bằng `take()`, dùng, rồi trả đối tượng theo giao thức. Với connection pool đã có thư viện quản lý giới hạn, không nên tự thêm một semaphore trùng vai trò mà chưa hiểu hai tầng sức chứa.

Nếu tài nguyên bị hỏng trong lúc dùng, việc trả giấy phép còn phải phù hợp với chính sách thay thế/giảm sức chứa của pool. Không trả quyền “có tài nguyên rảnh” trong khi thực tế pool chưa thể phục vụ lượt tiếp theo.

Ngoài ra, không giữ một khóa bảo vệ danh sách tài nguyên trong khi chờ giấy phép, nếu bên trả tài nguyên cần khóa đó để trả giấy phép. Hãy xét thứ tự tài nguyên và mọi bên có thể làm điểm chờ tiến triển.

## 9. Lấy nhiều giấy phép và chính sách công bằng

### Yêu cầu nhiều đơn vị cùng lúc

```java
slots.acquire(3);
try {
    useThreeUnits();
} finally {
    slots.release(3);
}
```

Đoạn minh họa chưa khai báo hàm nghiệp vụ và xử lý ngoại lệ. Khi lời gọi thành công, nó đã lấy đủ ba giấy phép. Không thay bằng ba lần `acquire()` riêng nếu thuật toán yêu cầu cấp nguyên một nhóm: các bên có thể giữ một phần giấy phép rồi cùng chờ phần còn lại.

Yêu cầu 3 giấy phép từ hệ thống chỉ có tổng sức chứa 2 sẽ không thể thành công, trừ khi một bên chủ động tăng số giấy phép theo giao thức. Cần kiểm tra cấu hình yêu cầu trước khi chờ.

### Công bằng không phải lịch hoàn tất

`new Semaphore(K)` mặc định không công bằng. `new Semaphore(K, true)` bật chính sách công bằng cho những thao tác lấy giấy phép được hợp đồng áp dụng.

Không suy ra từ đó rằng tác vụ gọi API sớm nhất theo thời gian đồng hồ chắc chắn chạy trước, hoặc tác vụ lấy giấy phép trước chắc chắn hoàn tất trước. Bộ lập lịch và thời gian công việc vẫn ảnh hưởng kết quả.

Đặc biệt, `tryAcquire()` không thời hạn có thể lấy giấy phép ngay cả khi có người đang chờ, theo hợp đồng của nó. Đừng gắn kỳ vọng xếp hàng tuyệt đối cho mọi phương thức chỉ từ cờ `true`.

Việc chọn công bằng cần xét yêu cầu chống chờ quá lâu và chi phí thông lượng, không dựa vào một quy tắc “luôn bật” hay “luôn tắt”.

## 10. Giới hạn đồng thời khác với các giới hạn khác

| Yêu cầu | Semaphore có tự đáp ứng không? |
| --- | --- |
| Tối đa K thao tác đang dùng tài nguyên cùng lúc | Có, nếu mọi bên lấy–trả đúng |
| Tối đa K yêu cầu mỗi giây | Không; cần giới hạn theo thời gian |
| Tối đa K tác vụ đang nằm trong hàng đợi executor | Không; cần quản lý hàng đợi/tiếp nhận |
| Đợi tất cả tác vụ đã hoàn tất | Không; dùng cơ chế hoàn tất |
| Bảo vệ ArrayList trước mọi cập nhật đồng thời | Không khi cho nhiều bên cùng vào; cần bảo vệ cấu trúc riêng |
| Giới hạn chung cho nhiều tiến trình/máy | Không chỉ bằng một Semaphore trong một JVM |

Giấy phép cần được giữ suốt thời gian tài nguyên thực sự bận. Với API bất đồng bộ, phương thức trả về một `Future` có thể chỉ là lúc công việc được bắt đầu, chưa phải lúc tài nguyên rảnh. Nếu trả giấy phép ngay khi nhận Future, giới hạn có thể bị vượt trong thực tế. Cần gắn việc trả với mốc hoàn tất thực sự và xử lý thành công/lỗi/hủy đúng một lần.

Đặt semaphore bên trong tác vụ giới hạn việc sử dụng tài nguyên, nhưng không tự hạn chế số tác vụ đã được submit. Nếu đầu vào không bị chặn hoặc từ chối ở đâu khác, hàng đợi vẫn có thể tăng không giới hạn.

## 11. Bộ nhớ và điều kiện tiến triển

Hợp đồng semaphore có quan hệ happens-before từ các hành động trước `release()` tới các hành động sau lần `acquire()` thành công tương ứng ở bên khác. Đây là quy tắc công bố bộ nhớ, không phải bảo đảm rằng mọi bên đang giữ các giấy phép khác nhau được loại trừ lẫn nhau.

Với K > 1, nhiều tác vụ vẫn có thể cùng sửa trạng thái chung. Semaphore chỉ giới hạn **bao nhiêu bên**, còn tính đúng của cập nhật bên trong là một câu hỏi khác.

Trước khi triển khai, hãy trả lời:

1. Một giấy phép đại diện cho tài nguyên hoặc quyền nào?
2. Sức chứa được xác định ở đâu?
3. Mọi đường vào vùng giới hạn có bắt buộc lấy giấy phép không?
4. Mốc nào chứng minh tài nguyên đã rảnh để trả?
5. Ai xử lý trả giấy phép khi lỗi, ngắt hoặc hủy?
6. Có đường nào trả hai lần hoặc trả khi chưa lấy không?
7. Bên đang chờ có giữ tài nguyên mà bên trả cần không?

Semaphore là bộ đếm quyền truy cập có đồng bộ. Giới hạn tài nguyên chỉ đáng tin khi quyền truy cập, vòng đời sử dụng và việc trả giấy phép được gắn với nhau bằng một giao thức rõ ràng.
