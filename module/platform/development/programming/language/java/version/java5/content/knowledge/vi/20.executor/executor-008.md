# Giới hạn hàng đợi hoặc số luồng khi chọn cấu hình

## 1. Vì sao cần giới hạn?

Executor tách nơi gửi công việc khỏi nơi thực hiện. Nhờ đó, bên gửi có thể tiếp tục tạo tác vụ trong khi các luồng xử lý việc trước đó. Nhưng nếu tốc độ tạo việc liên tục lớn hơn tốc độ xử lý, phần chênh lệch phải đi đâu đó:

- Tích tụ thành các tác vụ chờ trong bộ nhớ.
- Tạo thêm luồng để cố xử lý nhiều hơn.
- Làm bên gửi chậm lại.
- Hoặc bị từ chối theo một chính sách đã định.

Không có lựa chọn “nhận vô hạn nhưng không tốn tài nguyên”. Mục tiêu của giới hạn là giữ hệ thống trong khả năng xử lý và làm hành vi khi quá tải trở nên rõ ràng.

Trong bài này, **giới hạn luồng** nói đến số luồng của nhóm xử lý; **giới hạn hàng đợi** nói đến số tác vụ có thể nằm chờ trong hàng đợi của executor. Đây là hai đại lượng khác nhau.

Một nhóm có tối đa 8 luồng vẫn có thể giữ hàng trăm nghìn tác vụ chờ. Ngược lại, một hàng đợi không lưu phần tử vẫn có thể đi cùng chính sách tạo rất nhiều luồng.

## 2. Ba giới hạn cần nhìn cùng nhau

| Giới hạn | Nó bảo vệ điều gì? | Nó không tự bảo đảm điều gì? |
|---|---|---|
| Số luồng xử lý tối đa | Số luồng trong nhóm và một phần chi phí chuyển ngữ cảnh | Số việc đang chờ, dung lượng dữ liệu bị giữ |
| Dung lượng hàng đợi | Số phần tử chờ trong executor | Dung lượng byte của từng việc, thời gian chờ tối đa |
| Số truy cập tài nguyên ngoài | Số kết nối hoặc lời gọi nghiệp vụ đồng thời | Tổng số yêu cầu đã nhận vào ứng dụng |

Ví dụ, hàng đợi có 100 chỗ không có nghĩa chỉ giữ 100 KB. Mỗi tác vụ có thể giữ tham chiếu đến một mảng 10 MB, đối tượng yêu cầu hoặc dữ liệu lớn khác. Tương tự, 20 luồng không có nghĩa cơ sở dữ liệu đủ sức xử lý 20 truy vấn nặng đồng thời.

Cần hỏi rõ: **giới hạn này áp dụng ở đâu, đếm thứ gì và làm gì khi đạt ngưỡng?**

## 3. Các tham số của ThreadPoolExecutor

Khi cần kiểm soát trực tiếp, có thể dùng `java.util.concurrent.ThreadPoolExecutor` thay vì chỉ dùng factory cấu hình sẵn.

Ví dụ khai báo, chưa phải chương trình độc lập:

```java
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        4,                              // corePoolSize
        8,                              // maximumPoolSize
        30, TimeUnit.SECONDS,           // keepAliveTime
        new ArrayBlockingQueue<>(100),  // workQueue
        new ThreadPoolExecutor.AbortPolicy());
```

Các import nằm trong gói `java.util.concurrent`.

- `corePoolSize = 4`: mức luồng cốt lõi được dùng trong quy tắc nhận việc.
- `maximumPoolSize = 8`: giới hạn trên của số luồng trong nhóm.
- `keepAliveTime = 30 giây`: mặc định áp dụng cho luồng vượt mức core khi chúng rảnh; không phải thời hạn chạy của tác vụ.
- `ArrayBlockingQueue<>(100)`: tối đa 100 tác vụ chờ trong hàng đợi này.
- `AbortPolicy`: báo từ chối bằng `RejectedExecutionException`.

Không suy luận rằng khai báo core bằng bốn sẽ khởi động ngay bốn luồng. Mặc định, luồng được tạo theo nhu cầu; API có các thao tác khởi động trước nếu bài toán yêu cầu.

Các giá trị phải hợp lệ: core không âm, maximum dương và không nhỏ hơn core; dung lượng `ArrayBlockingQueue` phải dương.

## 4. Thứ tự nhận việc: core → queue → max → từ chối

Với executor đang hoạt động bình thường và factory tạo luồng thành công, có thể hiểu quy tắc theo thứ tự:

1. Số luồng hiện tại chưa đạt core: tạo thêm luồng để nhận tác vụ.
2. Đã đạt core: thử đưa tác vụ vào hàng đợi.
3. Không đưa được vào hàng đợi: thử tạo thêm luồng nếu chưa đạt maximum.
4. Không thể nhận thêm: gọi chính sách từ chối.

Vì vậy, executor **ưu tiên xếp hàng sau mức core**, chứ không luôn tăng lên maximum trước rồi mới xếp hàng.

Ví dụ core = 2, maximum = 4, queue capacity = 3. Giả sử các tác vụ trước vẫn đang bị giữ, chưa tác vụ nào kết thúc:

| Tác vụ gửi tiếp | Cách nhận |
|---|---|
| A | Tạo luồng thứ nhất |
| B | Tạo luồng thứ hai |
| C | Chờ trong hàng đợi |
| D | Chờ trong hàng đợi |
| E | Chờ trong hàng đợi; hàng đợi đã đủ ba phần tử |
| F | Tạo luồng thứ ba vì hàng đợi đầy |
| G | Tạo luồng thứ tư vì hàng đợi vẫn đầy |
| H | Bị từ chối nếu trạng thái vẫn chưa thay đổi |

Ở đây F có thể bắt đầu trước C dù được gửi sau. Hàng đợi FIFO không làm toàn bộ executor có thứ tự bắt đầu FIFO khi các tác vụ mới có thể được giao trực tiếp cho luồng mới.

Trong hệ thống thật, tác vụ có thể kết thúc xen kẽ lúc đang gửi. Bảng trên chỉ mô tả tình huống đã nêu, không phải công thức suy ra thứ tự từ số thứ tự yêu cầu.

Quy tắc phối hợp kích thước nhóm và hàng đợi được quy định trong [ThreadPoolExecutor API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html).

## 5. Hàng đợi không giới hạn khiến maximum không phát huy như dự kiến

Cấu hình sau dễ gây hiểu nhầm:

```java
ThreadPoolExecutor pool = new ThreadPoolExecutor(
        2,
        100,
        30, TimeUnit.SECONDS,
        new LinkedBlockingQueue<>());
```

`LinkedBlockingQueue` không truyền capacity có giới hạn mặc định rất lớn, thường được xem là hàng đợi không giới hạn trong thiết kế tải. Khi đã có hai luồng, các việc sau thường tiếp tục vào hàng đợi; executor không có lý do tăng lên 100 theo quy tắc “queue trước, max sau”.

Nói cách khác, đặt maximum lớn không tự khiến nhóm mở rộng khi số việc chờ tăng. Vấn đề là chính sách hàng đợi, không phải executor “bỏ qua” tham số một cách ngẫu nhiên.

Nếu cần hàng đợi liên kết có dung lượng rõ ràng, dùng `new LinkedBlockingQueue<>(capacity)`. Một lựa chọn khác là `ArrayBlockingQueue<>(capacity)`.

### So sánh các lựa chọn thường gặp

| Hàng đợi | Cách giữ việc | Ảnh hưởng tới cấu hình |
|---|---|---|
| `ArrayBlockingQueue<>(n)` | Mảng có dung lượng cố định, lấy phần tử theo FIFO | Có ngưỡng đầy để mở rộng luồng hoặc từ chối |
| `LinkedBlockingQueue<>(n)` | Hàng đợi liên kết có capacity tường minh | Cũng cho phép giới hạn việc chờ |
| `LinkedBlockingQueue<>()` | Capacity mặc định rất lớn | Dễ tích tụ việc; maximum thường không có tác dụng mở rộng |
| `SynchronousQueue<>()` | Chuyển giao trực tiếp, không chứa phần tử chờ | Cần luồng nhận ngay, thêm luồng hoặc từ chối |

`ArrayBlockingQueue` có các thao tác chờ như `put`, nhưng điều đó không có nghĩa `ThreadPoolExecutor.execute` sẽ tự chờ đến khi có chỗ. Đường nhận việc của executor dùng cách thử đưa vào hàng đợi rồi áp dụng quy tắc tiếp theo; khi đầy, nó có thể thêm luồng hoặc từ chối.

Hợp đồng hàng đợi được mô tả tại [ArrayBlockingQueue API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html).

Không tự gọi `pool.getQueue().put(task)` để lách quy trình nhận việc. Việc đó bỏ qua các kiểm tra vòng đời và chính sách quản lý tác vụ mà executor cung cấp.

## 6. Đọc đúng giới hạn của các factory

### newFixedThreadPool(n)

Factory giới hạn số luồng xử lý ở `n`, nhưng dùng hàng đợi không giới hạn dung lượng cấu hình sẵn. Thích hợp với tải đã được kiểm soát ở nơi khác; không đủ để kết luận hệ thống chịu được luồng yêu cầu không giới hạn.

`newSingleThreadExecutor()` cũng có vấn đề hàng đợi tương tự, dù chỉ xử lý từng việc một.

### newCachedThreadPool()

Factory giao việc trực tiếp và có thể tạo thêm luồng khi không có luồng rảnh. Nó không cung cấp một giới hạn số luồng hữu ích để bảo vệ ứng dụng trước đầu vào tăng mạnh.

Nếu các việc chặn lâu, số luồng nền tảng có thể tăng lớn, gây áp lực lên bộ nhớ và hệ điều hành. Việc không có hàng đợi lưu phần tử không đồng nghĩa không thể quá tải.

### Bộ thực thi định kỳ

`ScheduledThreadPoolExecutor` có cơ chế hàng đợi trễ riêng. Không áp dụng máy móc công thức “đặt maximum lớn để thêm luồng khi đầy” cho nó. Cần giới hạn số công việc lập lịch và kiểm soát công việc nghiệp vụ phát sinh từ từng lịch.

### Luồng ảo, Java 21+

`newVirtualThreadPerTaskExecutor()` tạo một luồng ảo cho mỗi tác vụ, không phải nhóm có kích thước cố định. Luồng ảo giảm chi phí chờ của luồng, nhưng không tăng vô hạn bộ nhớ, kết nối cơ sở dữ liệu hoặc năng lực dịch vụ ngoài.

Nếu cần giới hạn 20 lời gọi đồng thời tới một dịch vụ, hãy đặt giới hạn quanh việc truy cập tài nguyên ấy, thay vì tạo “pool 20 luồng ảo” chỉ để mô phỏng giới hạn tài nguyên.

## 7. Chính sách khi đạt ngưỡng

Hàng đợi hữu hạn cần đi kèm quyết định rõ ràng về tác vụ không nhận được.

| Chính sách | Hành vi chính | Điểm phải cân nhắc |
|---|---|---|
| `AbortPolicy` | Ném `RejectedExecutionException` | Nơi gửi phải xử lý thất bại tiếp nhận |
| `CallerRunsPolicy` | Chạy việc trên luồng đang gửi khi executor chưa đóng | Có thể làm bên gửi chậm; thay đổi nơi tác vụ chạy |
| `DiscardPolicy` | Bỏ tác vụ bị từ chối | Không phù hợp khi mọi việc đều cần được ghi nhận kết quả |
| `DiscardOldestPolicy` | Bỏ phần tử ở đầu hàng đợi rồi thử nhận việc mới khi executor chưa đóng | Có thể làm mất công việc đã được chấp nhận trước đó |

### AbortPolicy giúp thất bại trở nên nhìn thấy được

Nếu dùng chính sách này, không bắt ngoại lệ rồi bỏ qua. Tùy ngữ cảnh, ứng dụng có thể báo đang quá tải, ghi nhận yêu cầu chưa nhận, hoặc chuyển sang cơ chế lưu bền đã được thiết kế.

Thử lại ngay không giới hạn có thể làm tải nặng hơn. Nếu có retry, cần giới hạn số lần, khoảng chờ và điều kiện dừng phù hợp nghiệp vụ.

### CallerRunsPolicy không phải lựa chọn luôn an toàn

Khi executor bão hòa nhưng chưa đóng, bên gửi phải tự làm việc nên khó tiếp tục gửi nhanh như trước. Đây có thể tạo áp lực ngược (backpressure) trong một số mô hình.

Tuy nhiên, nếu bên gửi là luồng giao diện, luồng xử lý sự kiện hoặc đang giữ khóa quan trọng, chạy công việc nặng ngay tại đó có thể gây tắc nghẽn. Nhiều bên gửi cùng chạy tác vụ cũng có thể làm tổng số tác vụ thực thi vượt `maximumPoolSize`, vì những tác vụ này chạy ngoài nhóm luồng của executor.

Khi executor đã đóng, `CallerRunsPolicy` bỏ tác vụ thay vì chạy nó. Không dùng nó như bảo đảm “mọi việc luôn được thực hiện”. Xem [CallerRunsPolicy API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.CallerRunsPolicy.html).

### Bỏ tác vụ có thể làm Future không bao giờ hoàn tất

Với `submit`, tác vụ thường được bọc thành một đối tượng có theo dõi kết quả. Nếu chính sách âm thầm bỏ đối tượng này mà không chạy hoặc hủy nó, bên gọi vẫn có thể giữ một `Future` chưa hoàn tất.

Vì vậy, chính sách bỏ việc phải được thiết kế cùng hợp đồng kết quả. Không dùng discard để che lỗi quá tải đối với những công việc cần nhận kết quả đáng tin cậy.

## 8. Chương trình chứng minh giới hạn: hai luồng, hai chỗ chờ

Ví dụ sau dùng `CountDownLatch` để giữ các tác vụ đã bắt đầu. Khi gửi tác vụ thứ năm, chắc chắn hai luồng đã được cấp việc và hai chỗ chờ vẫn còn đầy. Không cần dựa vào một khoảng `sleep` đoán trước.

Lưu thành **`BoundedExecutorDemo.java`**, chạy trên Java 17+:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class BoundedExecutorDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch release = new CountDownLatch(1);
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1,
                2,
                30, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(2),
                new ThreadPoolExecutor.AbortPolicy());

        Runnable work = () -> {
            try {
                release.await();
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        };

        try {
            pool.execute(work); // A: first worker
            pool.execute(work); // B: queue slot 1
            pool.execute(work); // C: queue slot 2
            pool.execute(work); // D: second worker

            System.out.println("pool size: " + pool.getPoolSize());
            System.out.println("queued: " + pool.getQueue().size());

            try {
                pool.execute(work); // E: cannot be accepted
                throw new AssertionError("Expected rejection");
            } catch (RejectedExecutionException e) {
                System.out.println("E: rejected");
            }
        } finally {
            release.countDown();
            pool.shutdown();
            try {
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                    if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
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
javac --release 17 BoundedExecutorDemo.java
java BoundedExecutorDemo
```

Stdout chính xác:

```text
pool size: 2
queued: 2
E: rejected
```

Tác vụ A không thể hoàn tất trước khi mở chốt. Sau khi A được giao cho luồng đầu tiên, B và C vào hàng đợi. D không xếp hàng được nên được giao cho luồng thứ hai; D cũng bị giữ tại chốt. Vì không có luồng nào rảnh để lấy B hoặc C, trạng thái đầy được duy trì đến lúc E bị từ chối.

Trong `finally`, mở chốt để tất cả công việc đã nhận hoàn tất, rồi đóng executor. Việc đếm hàng đợi trong ví dụ đáng tin nhờ điều kiện đồng bộ đã thiết lập; trong ứng dụng đang chạy tự do, các số đo như `size()` và `getActiveCount()` chỉ phản ánh trạng thái tại thời điểm quan sát hoặc là ước lượng.

Đây là thí nghiệm về chính sách tiếp nhận, không phải cấu hình hiệu năng khuyến nghị cho ứng dụng thật.

## 9. Chọn dung lượng dựa trên thời gian chờ và bộ nhớ

### Hàng đợi không tạo thêm năng lực xử lý

Giả sử hệ thống xử lý ổn định khoảng 100 việc/giây nhưng nhận 150 việc/giây trong một khoảng dài. Nếu không có cơ chế giảm đầu vào, lượng tồn tăng khoảng 50 việc/giây. Tăng capacity chỉ trì hoãn thời điểm đầy; nó không làm năng lực xử lý thành 150 việc/giây.

Một hàng đợi lớn có thể hấp thụ đợt tăng ngắn, nhưng cũng có thể giữ những yêu cầu đã quá hạn sử dụng.

### Ước lượng đơn giản, rồi đo lại

Trong mô hình lý tưởng, nếu có 10 luồng, mỗi tác vụ mất khoảng 100 ms và còn 100 việc chờ phía trước, thời gian để đến lượt có thể ở mức khoảng một giây. Đây chỉ là ước lượng: thời gian xử lý không đều, I/O, khóa và tranh chấp tài nguyên đều làm kết quả khác đi.

Cần theo dõi ít nhất:

- Thời gian từ lúc tiếp nhận đến khi bắt đầu chạy.
- Thời gian thực thi.
- Số việc đang chờ và đang chạy.
- Tỷ lệ tác vụ bị từ chối hoặc hết thời gian chờ.
- Bộ nhớ và mức sử dụng tài nguyên liên quan.

Nếu độ trễ đã vượt yêu cầu nghiệp vụ, nhận thêm vào hàng đợi không nhất thiết có ích. Cấu hình phải gắn với thời hạn xử lý và cách phản hồi người dùng khi quá tải.

### Số luồng không chỉ phụ thuộc số CPU

Với việc chủ yếu tính toán, số lõi khả dụng là điểm khởi đầu để đánh giá mức song song. Với việc thường chờ I/O, có thể cần mức đồng thời khác, nhưng vẫn phải xét kết nối, giới hạn dịch vụ ngoài và thời hạn chờ. Không có một con số “tối ưu” đúng cho mọi hệ thống.

## 10. Giới hạn tài nguyên bằng Semaphore

Giả sử một executor xử lý nhiều loại công việc, nhưng chỉ được phép có tối đa 20 thao tác truy cập một dịch vụ ngoài cùng lúc. Có thể dùng `Semaphore` quanh vùng thực sự sử dụng dịch vụ đó.

Đoạn minh họa, không phải chương trình độc lập:

```java
Semaphore permits = new Semaphore(20);

// Ben trong tac vu:
permits.acquire();
try {
    callExternalService();
} finally {
    permits.release();
}
```

`callExternalService()` là thao tác nghiệp vụ do ứng dụng định nghĩa. Việc lấy permit phải thành công trước khi đi vào khối giải phóng; nếu `acquire()` bị ngắt, không được trả một permit chưa lấy.

Cách này giới hạn **số thao tác trong vùng bảo vệ**, không giới hạn tổng số tác vụ đã gửi. Nếu hàng nghìn tác vụ chờ permit thì chúng vẫn tồn tại và giữ bộ nhớ. Trên nhóm luồng nền tảng, các luồng chờ permit cũng đang chiếm chỗ trong nhóm.

Để giới hạn tổng số yêu cầu được nhận, cần cơ chế kiểm soát tiếp nhận ở đầu vào, chẳng hạn thử lấy quyền với thời hạn và từ chối khi không có chỗ. Nếu lấy permit trước khi gửi tác vụ, phải xử lý cả trường hợp gửi bị từ chối, tác vụ bị hủy hoặc không bao giờ bắt đầu để tránh rò rỉ permit.

Không thể chỉ thêm một `Semaphore` rồi bỏ qua toàn bộ vòng đời công việc. Hợp đồng của permit được mô tả trong [Semaphore API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Semaphore.html).

## 11. Các nhầm lẫn cần tránh

### Giới hạn số tác vụ đồng thời khác giới hạn tốc độ

Cho phép tối đa 20 thao tác đồng thời không tương đương tối đa 20 thao tác mỗi giây. Nếu mỗi việc hoàn tất rất nhanh, tốc độ có thể cao hơn nhiều. Một dịch vụ có hạn mức theo giây cần cơ chế kiểm soát tốc độ phù hợp.

### Queue hữu hạn không tự tạo backpressure

Với `AbortPolicy`, bên gửi nhận lỗi ngay khi không thể tiếp nhận. Nếu bên gửi bắt lỗi rồi lập tức gửi lại vô hạn, không có cơ chế giảm tải hữu ích nào được tạo ra. Phải thiết kế phản hồi ở nơi gửi.

Không tự viết handler chờ vô hạn bằng cách `put` lại vào queue mà chưa phân tích việc đóng executor và phụ thuộc giữa các tác vụ. Nếu chính luồng của nhóm bị giữ khi chờ một chỗ trong hàng đợi đầy, hệ thống có thể không tiến lên được.

### Hàng đợi trong bộ nhớ không phải nơi lưu công việc bền vững

Nếu cần bảo đảm công việc sống qua việc khởi động lại tiến trình, một `BlockingQueue` trong executor không đáp ứng yêu cầu đó. Cần thiết kế nơi lưu công việc và xử lý lại phù hợp; capacity của queue không thay thế cam kết lưu bền.

### Timeout chờ kết quả không tự dừng tác vụ

`future.get(timeout, unit)` hết hạn chỉ làm nơi gọi ngừng chờ bằng `TimeoutException`. Cần quyết định riêng về hủy tác vụ và xử lý ngắt; không giả định tác vụ đã biến mất khỏi hệ thống.

## 12. Tự kiểm tra

1. Core bằng 2, maximum bằng 10, hàng đợi không giới hạn: vì sao thường chỉ có hai luồng xử lý?
2. Với queue hữu hạn, executor mở rộng vượt core trước hay sau khi queue không nhận được thêm?
3. Vì sao `CallerRunsPolicy` có thể làm số tác vụ đang thực thi lớn hơn maximum của nhóm?
4. Hàng đợi 100 chỗ có bảo đảm giới hạn bộ nhớ ở một dung lượng cố định nhỏ không?
5. Dùng semaphore trong thân tác vụ có giới hạn số `Future` đã tạo không?
6. Nếu đầu vào cao hơn năng lực xử lý trong thời gian dài, tăng capacity có giải quyết được nguyên nhân không?

**Gợi ý:** (1) Công việc sau mức core tiếp tục được xếp hàng. (2) Sau khi không xếp hàng được. (3) Các bên gửi cũng tự chạy việc ngoài nhóm. (4) Không, mỗi tác vụ có thể giữ lượng dữ liệu khác nhau. (5) Không. (6) Không; cần giảm đầu vào, tăng năng lực thực hoặc từ chối có kiểm soát.

Một cấu hình hoàn chỉnh cần xác định **số luồng, dung lượng chờ, thời hạn có ích của công việc và cách phản hồi khi không thể nhận thêm**.
