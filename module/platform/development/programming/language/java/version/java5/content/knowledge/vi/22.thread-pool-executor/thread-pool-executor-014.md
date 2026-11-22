# Nguy cơ cạn luồng do tác vụ phụ thuộc lẫn nhau

## 1. Hết luồng khả dụng không nhất thiết do CPU quá tải

Một nhóm luồng có thể ngừng tạo tiến triển dù CPU còn rất rảnh. Nguyên nhân là mọi worker đang **chờ**, nhưng công việc cần để kết thúc việc chờ lại nằm trong hàng đợi của chính nhóm đó.

Ví dụ đơn giản:

1. Pool chỉ có một worker.
2. Tác vụ cha chạy trên worker ấy.
3. Cha gửi tác vụ con vào cùng pool.
4. Cha gọi `child.get()` để đợi kết quả.
5. Con phải đợi worker rảnh; worker lại đang bị cha giữ.

Đây thường được gọi là **bế tắc do cạn luồng thực thi (thread starvation deadlock)**. Tài nguyên bị giữ là khả năng thực hiện công việc của pool, không nhất thiết là một khóa Java.

Trong bài, “cạn luồng” nghĩa không còn worker khả dụng để thực hiện phần công việc cần cho tiến triển. Nó khác việc hệ điều hành không thể tạo thêm luồng vì hết bộ nhớ.

## 2. Chu trình chờ trong một pool một luồng

```text
Cha đang giữ worker duy nhất
        |
        v
Cha chờ Future của Con
        |
        v
Con nằm trong queue, cần một worker để chạy
        |
        v
Worker chỉ rảnh sau khi Cha kết thúc
        |
        +---------------------- quay lại Cha
```

Không có luồng rảnh để phá chu trình. Cha càng chờ lâu không làm con tự được thực thi.

Mã minh họa có vấn đề:

```java
ExecutorService pool = Executors.newSingleThreadExecutor();

Future<Integer> parent = pool.submit(() -> {
    Future<Integer> child = pool.submit(() -> 21);
    return child.get() * 2;
});

Integer result = parent.get();
```

Đây là đoạn minh họa lỗi, **không nên chạy nguyên trạng với các lời chờ không giới hạn**. Phần sau có chương trình có timeout và dọn dẹp rõ để quan sát an toàn.

`Future.get()` chờ kết quả; nó không có hợp đồng chung là tự lấy công việc trong queue của ThreadPoolExecutor ra để làm thay. Xem [Future API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html).

## 3. Pool nhiều luồng vẫn có thể mắc kẹt

Tăng từ một lên bốn luồng không loại bỏ cấu trúc phụ thuộc.

Giả sử bốn worker đều đang chạy bốn tác vụ cha. Mỗi cha gửi một con rồi chờ. Bốn con nằm trong queue; không còn worker nào rảnh để chạy chúng.

Điều kiện nguy hiểm thường là:

- Nhóm có số worker hữu hạn.
- Công việc đang chạy giữ worker trong lúc chờ.
- Sự kiện kết thúc lời chờ cần công việc khác được chính nhóm đó thực hiện.
- Không còn năng lực thực thi cho công việc tạo sự kiện.

Phụ thuộc cũng có thể sâu nhiều tầng. Nếu mỗi cha sinh con và mỗi con lại sinh cháu rồi đứng chờ, một cấu hình đủ cho thử nghiệm nhỏ có thể hết chỗ khi tải hoặc độ sâu tăng.

Vì vậy, kiểm thử với một yêu cầu thành công không chứng minh mô hình phụ thuộc an toàn khi có nhiều yêu cầu đồng thời.

## 4. Vì sao maximum lớn hơn core chưa chắc giúp?

ThreadPoolExecutor thường nhận công việc theo thứ tự:

1. Tạo thêm worker nếu chưa đạt core.
2. Sau core, thử đưa việc vào queue.
3. Chỉ khi queue không nhận được mới thử mở rộng tới maximum.
4. Nếu không thể nhận thêm, áp dụng handler từ chối.

Ví dụ core bằng 2, maximum bằng 20 nhưng queue không giới hạn dung lượng cấu hình sẵn. Hai cha giữ hai worker; các con vẫn xếp hàng được nên pool không tự tạo thêm worker chỉ vì có cha đang gọi get.

Đặt maximum lên 100 không làm lời chờ biến mất nếu quy tắc vẫn đưa mọi con vào queue.

Tài liệu ThreadPoolExecutor lưu ý sự tương tác giữa loại queue và những nhóm công việc có phụ thuộc nội bộ; xem [ThreadPoolExecutor API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html).

### Queue nhỏ hoặc chuyển giao trực tiếp có phải cách sửa hoàn chỉnh?

Queue nhỏ hoặc `SynchronousQueue` có thể làm executor mở rộng thay vì xếp các việc phụ thuộc vào queue. Nhưng nếu đã đạt maximum thì vẫn phải từ chối hoặc xử lý theo handler.

Nếu cho phép tăng luồng rất lớn để tránh chờ, nguy cơ có thể chuyển thành tăng quá nhiều luồng và tài nguyên. Không thay một chu trình chờ bằng tăng tài nguyên không kiểm soát rồi coi là đã giải quyết mọi trường hợp.

Cấu trúc phụ thuộc cần được phân tích trước khi chỉnh số luồng.

## 5. Thí nghiệm Java 17+: con nằm chờ trong chính pool của cha

Chương trình có một worker, quan sát trạng thái bị chặn bằng một lần get có timeout, rồi hủy phần thử nghiệm. Sau đó nó thực hiện cách điều phối không giữ worker để chờ việc con.

Lưu thành **`PoolDependencyDemo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicReference;

public class PoolDependencyDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1,
                1,
                0, TimeUnit.SECONDS,
                new LinkedBlockingQueue<>());

        AtomicReference<Future<Integer>> childHandle =
                new AtomicReference<>();
        CountDownLatch childSubmitted = new CountDownLatch(1);
        CountDownLatch parentExited = new CountDownLatch(1);
        Future<Integer> parent = null;

        try {
            parent = pool.submit(() -> {
                try {
                    Future<Integer> child = pool.submit(() -> 21);
                    childHandle.set(child);
                    childSubmitted.countDown();
                    return child.get() * 2;
                } finally {
                    parentExited.countDown();
                }
            });

            if (!childSubmitted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Child was not submitted");
            }

            System.out.println(
                    "queued children: " + pool.getQueue().size());
            System.out.println("parent done: " + parent.isDone());

            try {
                parent.get(50, TimeUnit.MILLISECONDS);
                throw new AssertionError("Expected blocked dependency");
            } catch (TimeoutException e) {
                System.out.println("observation: timeout");
            }

            parent.cancel(true);
            childHandle.get().cancel(false);

            if (!parentExited.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Parent did not respond to interruption");
            }

            Future<Integer> independent = pool.submit(() -> 21);
            int correctedResult =
                    independent.get(5, TimeUnit.SECONDS) * 2;
            System.out.println("orchestrated result: " + correctedResult);
        } finally {
            if (parent != null && !parent.isDone()) {
                parent.cancel(true);
            }
            Future<Integer> child = childHandle.get();
            if (child != null && !child.isDone()) {
                child.cancel(false);
            }

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
javac --release 17 PoolDependencyDemo.java
java PoolDependencyDemo
```

Stdout chính xác:

```text
queued children: 1
parent done: false
observation: timeout
orchestrated result: 42
```

### Đọc diễn biến

Chốt `childSubmitted` xác nhận con đã được gửi. Cha chưa thể hoàn tất vì nó chỉ có kết quả sau con; con không thể chạy vì cha đang giữ worker duy nhất.

Timeout 50 ms không phải dùng để đoán tác vụ nào chạy trước. Trong cấu trúc này, không có đường tiến triển bình thường trước khi main can thiệp.

Hủy cha với yêu cầu ngắt làm lời chờ get trong cha thoát. Chốt `parentExited` giúp main biết thân cha đã đi qua finally, thay vì chỉ nhìn trạng thái Future đã hủy.

Phần đúng đặt lời chờ ở main: main không chiếm worker của pool. Worker thực hiện phép tính 21, còn main nhận giá trị rồi tính thành 42.

Các lời chờ năm giây giúp báo lỗi nếu thí nghiệm không tiến triển. Main khai báo throws Exception để tập trung vào cấu trúc phụ thuộc; ứng dụng thật cần đường phản hồi ngắt, lỗi kết quả và lỗi tiếp nhận phù hợp.

## 6. Hướng sửa thứ nhất: điều phối ngoài worker hữu hạn

Nếu một thành phần có nhiệm vụ điều phối nhiều công việc, có thể để nó gửi các việc con rồi thu kết quả từ một nơi không chiếm worker đang cần cho các việc ấy.

Ví dụ minh họa:

```java
Future<PartA> a = workers.submit(this::computeA);
Future<PartB> b = workers.submit(this::computeB);

PartA partA = a.get();
PartB partB = b.get();
return combine(partA, partB);
```

`PartA`, `PartB`, `computeA`, `computeB` và `combine` thuộc ứng dụng. Đoạn này chỉ đúng về hướng tránh giữ worker **nếu nơi điều phối không nằm trên chính pool hữu hạn cần chạy A và B**.

Chuyển cùng đoạn mã vào một tác vụ của pool ấy có thể đưa vấn đề quay lại.

Nếu không thực sự cần tách công việc nhỏ thành tác vụ khác, gọi phương thức trực tiếp trong cha có thể đơn giản hơn. Không tạo thêm một bước submit rồi chờ chỉ để mang nhãn bất đồng bộ.

## 7. Hướng sửa thứ hai: nối bước thay vì chặn trong worker

Với các công việc phụ thuộc nhau theo kết quả, có thể tổ chức các bước tiếp theo chỉ chạy khi dữ liệu trước sẵn sàng, thay vì một worker ngồi chờ get hoặc join.

Ví dụ minh họa Java 17+:

```java
CompletableFuture<Integer> base =
        CompletableFuture.supplyAsync(() -> 21, workers);

CompletableFuture<Integer> result =
        base.thenApply(value -> value * 2);
```

Đây chưa phải chương trình độc lập; executor do ứng dụng quản lý. Bước nhân hai được mô tả là hành động phụ thuộc, không cần giữ một tác vụ cha trong pool để chờ base.

Tuy nhiên, đổi `Future.get()` thành `CompletableFuture.join()` bên trong worker không tự sửa cạn luồng: join vẫn có thể chờ kết quả.

Các callback cũng không nên tạo một vòng phụ thuộc mới rồi chặn. Khi cần phối hợp bất đồng bộ nhiều bước, chọn các phương thức ghép bước phù hợp và hiểu executor mà các bước sử dụng.

Khả năng nối bước được mô tả trong [CompletableFuture API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CompletableFuture.html).

## 8. Hướng sửa thứ ba: tách vai trò và tài nguyên có kiểm soát

Có thể tách nơi điều phối và nơi thực thi phần công việc khác nhau, nhưng “thêm pool thứ hai” không phải bảo đảm chung.

Ví dụ:

```text
Pool A: cha chờ công việc ở Pool B
Pool B: con chỉ xử lý rồi kết thúc
```

Cấu trúc có thể tiến triển nếu B được cấp tài nguyên phù hợp và không chờ ngược A.

Nhưng nếu công việc B lại gửi việc về A rồi đợi, có thể hình thành chu trình chờ qua hai pool.

Tương tự, cha đang giữ một kết nối cơ sở dữ liệu rồi chờ con xin kết nối từ pool đã hết có thể mắc kẹt dù con có worker rảnh. Cần vẽ cả tài nguyên bên ngoài:

```text
Cha giữ kết nối -> chờ Con
Con có worker -> chờ kết nối Cha đang giữ
```

Phân tích phải xét worker, khóa, permit, kết nối và đường hoàn tất của từng lời chờ, không chỉ đếm số luồng.

## 9. Timeout và handler là ranh giới thất bại, không phải thiết kế tiến triển

### Timeout có ích để không chờ vô hạn

Get có timeout giúp nơi chờ phát hiện không có kết quả trong ngân sách. Nhưng sau timeout, tác vụ con không tự bị hủy; cha cũng có thể vẫn giữ worker nếu mã chỉ ghi log rồi chờ lại.

Cần quyết định rõ cách thoát, hủy phần còn lại và xử lý tác động đã có. Retry toàn bộ ngay có thể đưa thêm công việc vào một pool đang bế tắc.

### CallerRunsPolicy không phải lời giải tổng quát

Nếu queue đầy và policy cho bên gửi chạy con ngay, nó có thể làm một tình huống cha-con cụ thể tiến triển. Nhưng hành vi phụ thuộc trạng thái queue và vòng đời executor.

Với queue còn chỗ, con có thể vẫn được xếp hàng và cha vẫn chờ. Với tác vụ giữ khóa hoặc phụ thuộc tín hiệu từ bên gửi, chạy ngay cũng có thể tạo vấn đề khác.

Không dựa vào một handler như cách chứng minh mọi đồ thị phụ thuộc đều an toàn.

### Tăng worker có thể chỉ dời ngưỡng lỗi

Một cấu hình lớn hơn có thể vượt qua thử nghiệm nhỏ nhưng vẫn mắc kẹt khi đủ số cha đồng thời lấp đầy nhóm. Cần sửa nơi chờ hoặc cấu trúc công việc, rồi mới định cỡ tài nguyên theo tải.

## 10. Dấu hiệu chẩn đoán

Các dấu hiệu thường xuất hiện cùng nhau:

- Queue có công việc chưa bắt đầu.
- Mọi worker đều chờ Future, latch, semaphore hoặc tài nguyên.
- Số công việc hoàn tất không tăng.
- CPU không nhất thiết cao.
- Tăng thời gian chờ không tạo thêm kết quả.

Cần lấy thread dump để xem worker đang chờ ở đâu, rồi nối lời chờ ấy với công việc hoặc tài nguyên có thể giải phóng nó.

Tên worker và mã công việc giúp liên kết: “cha đang chờ Future nào, con nằm ở executor nào, executor đó còn worker khả dụng không?”

### Không có báo deadlock khóa chưa chắc an toàn

Các cơ chế như `ThreadMXBean.findDeadlockedThreads()` tập trung vào chu trình chờ monitor hoặc ownable synchronizer theo hợp đồng của chúng. Một chu trình cạn worker với Future có thể không được báo như deadlock khóa thông thường.

Vì vậy, kết quả không tìm thấy deadlock không đủ để kết luận nhóm luồng đang tạo tiến triển.

Khả năng và phạm vi phát hiện được mô tả trong [ThreadMXBean API](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadMXBean.html).

## 11. Fork/Join và luồng ảo cần hiểu theo mô hình riêng

Không áp dụng máy móc hành vi của ThreadPoolExecutor một luồng cho mọi runtime.

Fork/Join có cơ chế phối hợp công việc và hỗ trợ riêng cho một số kiểu chờ, nhưng điều đó không có nghĩa mọi I/O, khóa hoặc phụ thuộc tùy ý đều tự an toàn.

Với Java 21+, mô hình mỗi tác vụ một luồng ảo có thể phù hợp cho nhiều công việc chặn. Một luồng ảo chờ trong thao tác hỗ trợ phù hợp không nhất thiết giữ riêng một luồng hệ điều hành suốt thời gian ấy.

Nhưng luồng ảo không phá chu trình phụ thuộc logic, không tăng số kết nối cơ sở dữ liệu và không giải phóng permit cha đang giữ cho con. Đặt một semaphore hữu hạn rồi để tất cả cha giữ permit trong khi chờ con cũng có thể tạo thiếu năng lực tiến triển.

Hướng sử dụng được trình bày trong [hướng dẫn Virtual Threads của Oracle](https://docs.oracle.com/en/java/javase/25/core/virtual-threads.html).

## 12. Tự kiểm tra

1. Vì sao một worker chờ child.get có thể làm con không bao giờ chạy?
2. Pool có 8 luồng có luôn tránh được lỗi nếu 8 cha đồng thời đều chờ con trong cùng pool không?
3. Maximum bằng 100 có giúp khi mọi con vẫn xếp được vào queue sau mức core không?
4. Đổi get thành join mà vẫn chặn trong worker có tự sửa cấu trúc phụ thuộc không?
5. Timeout của main có tự hủy các công việc đang mắc kẹt không?
6. Không tìm thấy deadlock khóa có chứng minh hệ thống không bị cạn worker do phụ thuộc không?

**Gợi ý:** (1) Cha giữ tài nguyên con cần để chạy. (2) Không. (3) Không tự động. (4) Không. (5) Không. (6) Không.

Trước mỗi lời chờ trong worker, cần trả lời được: **sự kiện mình đang đợi do ai tạo ra, và bên ấy còn đủ tài nguyên để chạy khi mình đang giữ chỗ này không?**
