# Thực hành tổng hợp: Producer–Consumer với BlockingQueue trong Java 17

## 1. Đề bài và yêu cầu

Xây dựng mô hình **sản xuất–tiêu thụ (producer–consumer)**, trong đó producer tạo công việc và consumer xử lý công việc trên các luồng khác nhau. Nếu hai phía chạy với tốc độ khác nhau, dữ liệu phải được trao đổi an toàn: producer chờ khi vùng đệm đầy, consumer chờ khi chưa có công việc, và chương trình có cách kết thúc rõ ràng.

Yêu cầu cụ thể của bài thực hành:

- **2 producer**, mỗi producer sinh **6 công việc** có định danh riêng; tổng cộng **12 công việc**.
- **3 consumer** lấy và xử lý các công việc song song.
- Vùng đệm chỉ giữ tối đa **4 công việc** đang chờ, tránh phát sinh hàng đợi vô hạn khi producer nhanh hơn consumer.
- Chờ toàn bộ producer xong mới phát tín hiệu dừng; mọi consumer phải thoát được.
- Tổng hợp số lượng đã xử lý và kiểm tra hàng đợi rỗng sau khi kết thúc.

Trọng tâm là `BlockingQueue`, `ArrayBlockingQueue`, `put`, `take`, *backpressure*, `ExecutorService`, `Future` và cơ chế **poison pill**. Không cần tự dùng `synchronized`, `wait()` hoặc `notify()` để cài đặt vùng đệm.

## 2. Mô hình và nguyên lý

~~~text
Producer 1 ──┐
             ├── put() ──> [ ArrayBlockingQueue, capacity = 4 ] ── take() ──> Consumer 1
Producer 2 ──┘                                          ├─ take() ──> Consumer 2
                                                       └─ take() ──> Consumer 3
~~~

`BlockingQueue<E>` là một giao diện hàng đợi an toàn khi nhiều luồng cùng truy cập. `ArrayBlockingQueue` triển khai hàng đợi FIFO có dung lượng cố định:

- `put(e)` đưa công việc vào hàng đợi. Khi đầy, producer **chờ** đến khi có chỗ hoặc bị ngắt.
- `take()` lấy công việc khỏi hàng đợi. Khi rỗng, consumer **chờ** đến khi có phần tử hoặc bị ngắt.
- Queue tự bảo đảm đồng bộ cho các thao tác của chính nó. Người dùng không phải tự khóa quanh từng lệnh `put` và `take`.

Khi consumer xử lý chậm, bốn vị trí chờ có thể đầy và producer bị chặn tại `put`. Đây là **backpressure**: hệ thống giới hạn số lượng công việc đang xếp hàng và làm chậm phía cung cấp khi phía xử lý chưa theo kịp. Sức chứa 4 chỉ đếm công việc *nằm trong queue*, không bao gồm công việc đã được lấy ra và đang xử lý.

Consumer **không thể coi queue đang rỗng là producer đã làm xong**, vì một producer có thể bổ sung công việc ngay sau đó. Chương trình dùng một đối tượng riêng `STOP` (poison pill) để thông báo kết thúc. Trình tự bắt buộc:

1. Các producer đưa mọi công việc thật vào queue.
2. Luồng main chờ từng `Future` của producer hoàn tất.
3. Main đưa **một tín hiệu `STOP` cho mỗi consumer** vào sau các công việc thật.
4. Mỗi consumer đọc được `STOP` thì thoát; main chờ kết quả của cả ba consumer.

Do hàng đợi FIFO, các công việc thật đã đưa vào trước `STOP` sẽ được lấy ra trước tín hiệu này. Ba consumer cần ba tín hiệu để không ai tiếp tục chờ ở `take()` vô hạn.

## 3. Cài đặt hoàn chỉnh chạy trên Java 17+

Tạo tệp **`BlockingQueueDemo.java`** với nội dung sau. `Job` là một `record` bất biến, chứa ID producer và số thứ tự để nhận diện từng công việc. Pool dùng **5 luồng** để đủ chỗ chạy đồng thời cả hai producer và ba consumer; submit consumer trước giúp sẵn sàng đón việc.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

public class BlockingQueueDemo {
    private static final int PRODUCER_COUNT = 2;
    private static final int CONSUMER_COUNT = 3;
    private static final int JOBS_PER_PRODUCER = 6;
    private static final int QUEUE_CAPACITY = 4;

    private record Job(int producerId, int sequence) {}

    // Tín hiệu dừng: chỉ đưa vào queue sau khi mọi producer hoàn tất.
    private static final Job STOP = new Job(-1, -1);

    public static void main(String[] args)
            throws InterruptedException, ExecutionException {

        BlockingQueue<Job> queue = new ArrayBlockingQueue<>(QUEUE_CAPACITY);
        ExecutorService pool = Executors.newFixedThreadPool(
                PRODUCER_COUNT + CONSUMER_COUNT);

        List<Future<?>> producers = new ArrayList<>();
        List<Future<Integer>> consumers = new ArrayList<>();

        try {
            for (int i = 1; i <= CONSUMER_COUNT; i++) {
                final int consumerId = i;

                consumers.add(pool.submit(() -> {
                    int processed = 0;
                    while (true) {
                        Job job = queue.take();  // Đợi nếu queue rỗng.

                        if (job == STOP) {
                            return processed;
                        }

                        System.out.printf(
                                "Consumer-%d xử lý P%d-#%d%n",
                                consumerId, job.producerId(), job.sequence());

                        // Giả lập một công việc tương đối chậm.
                        Thread.sleep(50);
                        processed++;
                    }
                }));
            }

            for (int i = 1; i <= PRODUCER_COUNT; i++) {
                final int producerId = i;

                producers.add(pool.submit(() -> {
                    for (int n = 1; n <= JOBS_PER_PRODUCER; n++) {
                        queue.put(new Job(producerId, n)); // Đợi nếu đầy.
                    }
                    return null;
                }));
            }

            // get() chờ producer xong và bộc lộ lỗi trong task.
            for (Future<?> producer : producers) {
                producer.get();
            }

            // Có ba consumer nên phải có đúng ba tín hiệu dừng.
            for (int i = 0; i < CONSUMER_COUNT; i++) {
                queue.put(STOP);
            }

            int processedTotal = 0;
            for (Future<Integer> consumer : consumers) {
                processedTotal += consumer.get();
            }

            int expected = PRODUCER_COUNT * JOBS_PER_PRODUCER;
            if (processedTotal != expected || !queue.isEmpty()) {
                throw new IllegalStateException(
                        "Sai số lượng: processed=" + processedTotal
                                + ", queueSize=" + queue.size());
            }

            System.out.printf(
                    "Hoàn tất: %d/%d công việc; hàng đợi còn %d phần tử%n",
                    processedTotal, expected, queue.size());
        } finally {
            // Đánh thức các task có thể đang kẹt trong put/take/sleep
            // nếu producer hoặc consumer gặp lỗi hay main bị interrupt.
            // Với lượt chạy thành công, các Future đều đã hoàn thành.
            pool.shutdownNow();
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac BlockingQueueDemo.java
java BlockingQueueDemo
~~~

Ví dụ một phần kết quả:

~~~text
Consumer-2 xử lý P1-#1
Consumer-1 xử lý P2-#1
...
Hoàn tất: 12/12 công việc; hàng đợi còn 0 phần tử
~~~

Chương trình in **12 dòng xử lý** và cuối cùng in **`12/12`**, hàng đợi còn **0** phần tử khi chạy bình thường. Thứ tự các dòng xử lý (và consumer nào nhận từng việc) **không cố định**, phụ thuộc lịch chạy của các luồng. Những dòng minh họa đầu tiên không phải đầu ra bắt buộc; dòng kết luận là bất biến cần kiểm tra.

## 4. Giải thích chi tiết từng giai đoạn

**Consumer khởi động:** Các consumer gọi `queue.take()` trong vòng lặp; nếu chưa có việc, luồng được chặn mà không phải liên tục hỏi `isEmpty()`. Consumer chỉ trở lại làm việc khi phần tử xuất hiện hoặc luồng bị interrupt.

**Producer đưa việc vào:** Hai producer tạo đúng các cặp ID `(1,1)` đến `(1,6)` và `(2,1)` đến `(2,6)`. Khi queue đủ bốn công việc đang chờ, `put()` bị chặn. Một consumer lấy ra một phần tử sẽ giải phóng vị trí cho producer. `Thread.sleep(50)` chỉ mô phỏng thời gian xử lý để dễ quan sát quá tải; queue không yêu cầu sleep để vận hành.

**Main xác định thời điểm có thể dừng:** `producer.get()` chờ producer hoàn thành hoặc ném `ExecutionException` nếu task thất bại. Vì main đợi tất cả producer trước khi gửi `STOP`, không có công việc thật của các producer này được xếp vào queue phía sau tín hiệu dừng.

**Consumer nhận tín hiệu:** Mỗi `STOP` đi qua queue như một phần tử bình thường, nhưng consumer nhận diện rồi **trả về ngay** thay vì xử lý hay cộng bộ đếm. So sánh `job == STOP` là có chủ ý: cả ba tín hiệu đều là **chính cùng đối tượng** sentinel; các producer chỉ tạo đối tượng `Job` mới với ID dương.

**Main kiểm tra kết quả:** Khi cả ba `consumer.get()` trả về, các consumer đã dừng. Mỗi lần consumer xử lý xong một việc thật, nó tăng bộ đếm của riêng mình; main cộng các bộ đếm thành `processedTotal`. Chỉ sau khi mọi task hoàn tất mới kiểm tra `queue.isEmpty()`; kiểm tra `size()` hoặc `isEmpty()` khi các luồng còn chạy sẽ không cho biết trạng thái cuối cùng ổn định.

**Dọn tài nguyên:** `shutdownNow()` ở `finally` gọi interrupt lên các task còn chạy. `put`, `take` và `sleep` là các lệnh có thể bị interrupt. Với chương trình minh họa thành công, main đã đợi mọi Future hoàn tất trước khi giải phóng pool. Với dịch vụ chạy lâu, cần bổ sung quy trình dừng có thời hạn, ghi nhận thất bại và giám sát các task không phản hồi interrupt.

**Tính nhìn thấy bộ nhớ:** Các thao tác trước khi một phần tử được đưa vào `BlockingQueue` có quan hệ *happens-before* với thao tác của luồng khác sau khi phần tử đó được lấy ra. Tuy vậy, queue chỉ bảo đảm an toàn của thao tác hàng đợi; nếu nhiều luồng cùng sửa một payload mutable thì vẫn cần cơ chế đồng bộ hoặc thiết kế bất biến. `record Job` tránh chia sẻ trạng thái mutable trong bài này.

## 5. Những API liên quan và cách chọn

| Tác vụ | API | Khi queue đầy/rỗng |
| --- | --- | --- |
| Đưa phần tử và sẵn sàng chờ | `put(e)` | Chờ khi đầy; có thể ném `InterruptedException` |
| Thử đưa ngay | `offer(e)` | Trả `false` nếu đầy |
| Đưa với thời gian chờ tối đa | `offer(e, time, unit)` | Hết hạn trả `false`, cũng có thể bị interrupt |
| Lấy phần tử và sẵn sàng chờ | `take()` | Chờ khi rỗng; có thể ném `InterruptedException` |
| Thử lấy ngay | `poll()` | Trả `null` nếu rỗng |
| Lấy với thời gian chờ tối đa | `poll(time, unit)` | Hết hạn trả `null`, cũng có thể bị interrupt |

`add(e)` có thể ném `IllegalStateException` nếu hàng đợi bounded đã đầy, trong khi `remove()` không đối số ném `NoSuchElementException` nếu hàng đợi rỗng. Chúng không thay thế `put/take` trong mô hình cần chờ có kiểm soát.

Ví dụ dùng timeout (**đoạn minh họa**; `queue` và `job` phải được khai báo trong ngữ cảnh gọi):

~~~java
boolean accepted = queue.offer(
        job, 200, java.util.concurrent.TimeUnit.MILLISECONDS);
if (!accepted) {
    // Hết thời gian chờ: thông báo quá tải hoặc thử lại có giới hạn.
}

Job next = queue.poll(
        300, java.util.concurrent.TimeUnit.MILLISECONDS);
if (next == null) {
    // Chưa có công việc; KHÔNG có nghĩa mọi producer đã kết thúc.
}
~~~

Cả hai overload có timeout có thể ném `InterruptedException`. Khi xử lý interrupt trong một task, thường cần cho exception lan ra hoặc khôi phục trạng thái bằng `Thread.currentThread().interrupt()` rồi thoát một cách phù hợp. **Không âm thầm nuốt interrupt** và chạy tiếp mãi.

## 6. Các lỗi thực tế dễ gặp

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Consumer thấy `queue.isEmpty()` rồi tự thoát | Queue tạm rỗng nhưng producer có thể còn đang tạo việc | Phân biệt chưa có việc với hết nguồn; dùng giao thức dừng |
| Đưa `STOP` trước khi mọi producer kết thúc | Consumer có thể dừng trước khi xử lý hết dữ liệu | Đợi đủ `producer.get()` rồi mới gửi |
| Chỉ đưa một `STOP` cho ba consumer | Các consumer còn lại có thể kẹt ở `take()` | Một poison pill cho mỗi consumer |
| Pool chỉ có 2 thread, submit cả hai producer trước consumer | Hai producer có thể chặn khi queue đầy, khiến consumer không có thread để chạy | Dùng pool đủ chỗ hoặc pool riêng cho từng vai trò |
| Dùng queue không giới hạn khi nguồn việc tăng nhanh | Công việc tồn đọng có thể tăng bộ nhớ vô hạn | Chọn dung lượng bounded và chính sách backpressure |
| Tự kiểm tra `remainingCapacity()` rồi mới `put()` | Kết quả kiểm tra đã có thể thay đổi bởi luồng khác | Dùng ngay `put` hoặc `offer` nguyên tử |
| Gọi `shutdown()` và kỳ vọng `take()` tự trả về | `shutdown()` dừng việc nhận task mới, không phải tín hiệu cuối luồng cho queue | Dùng sentinel hoặc interrupt có quản lý |
| Bỏ qua `ExecutionException` hay `InterruptedException` | Không quan sát được lỗi, task có thể chờ không kết thúc | Xử lý lỗi, đóng worker, báo trạng thái rõ ràng |
| Giả định BlockingQueue tự lưu bền/retry/ack | Dữ liệu vẫn có thể mất khi JVM chết hoặc worker thất bại | Thiết kế retry, lưu bền, xác nhận xử lý hoặc message broker nếu cần |

Trong `LinkedBlockingQueue`, nếu không truyền capacity thì mặc định rất lớn (`Integer.MAX_VALUE`), nên dễ bỏ lỡ nhu cầu kiểm soát tồn đọng. `ArrayBlockingQueue` với capacity cụ thể cho thấy backpressure rõ ràng. Tham số fairness của `ArrayBlockingQueue` có thể ảnh hưởng thứ tự luồng được phục vụ, **không** bảo đảm thứ tự in kết quả hay cải thiện hiệu năng trong mọi trường hợp.

## 7. Bài tập kiểm chứng và mở rộng

1. **Tăng sức ép lên queue:** đặt `QUEUE_CAPACITY = 1`, đổi thời gian xử lý thành `Thread.sleep(300)`. Giải thích tại sao tổng kết vẫn là 12 công việc và tại sao producer có thể chờ lâu hơn.
2. **Tăng quy mô:** thử 4 producer, 2 consumer, 10 việc/producer. Kết quả hợp lệ cuối chương trình là **`40/40`**. Phải điều chỉnh số sentinel thành 2 và đủ luồng trong pool.
3. **Chính sách quá tải:** thay `put()` bằng `offer(e, timeout, unit)` và chủ động quyết định khi quá thời hạn. Nếu bỏ một việc, phải thống kê việc bị từ chối; không được báo số lượng xử lý như thể mọi công việc đều đã được chấp nhận.
4. **Phát hiện lặp:** bổ sung `ConcurrentHashMap.newKeySet()` để lưu các cặp mã công việc đã được xử lý; kiểm tra `add` không trả false và tập cuối chứa đủ các mã hợp lệ. Kiểm tra này mạnh hơn đối chiếu mỗi tổng bộ đếm.
5. **Thử lỗi producer:** cố ý ném exception ở một producer và quan sát `Future.get()` trả lỗi `ExecutionException`, `finally` yêu cầu hủy các task đang chờ. Đề xuất một quy trình báo lỗi, retry và dừng dịch vụ thích hợp cho production.

**Tiêu chí hoàn thành:** biên dịch và chạy được Java 17+, kết thúc bình thường với **12/12 công việc**, queue rỗng; đồng thời giải thích được `put/take`, backpressure, thời điểm gửi poison pill, số poison pill tương ứng số consumer, và cách xử lý interrupt. Đây là mô hình phối hợp luồng **trong một tiến trình**: không tự cung cấp cơ chế lưu bền, transaction, retry hay bảo đảm xử lý chính xác một lần khi hệ thống gặp sự cố.
