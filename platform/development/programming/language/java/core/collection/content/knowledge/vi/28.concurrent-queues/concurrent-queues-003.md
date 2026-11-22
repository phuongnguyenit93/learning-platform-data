# Hàng đợi có giới hạn và điều tiết tốc độ bên sản xuất

Trong mô hình sản xuất–tiêu thụ (producer–consumer), bên sản xuất tạo công việc, đưa vào hàng đợi, còn bên tiêu thụ lấy ra để xử lý. Hai bên không nhất thiết hoạt động cùng tốc độ.

Nếu bên sản xuất liên tục tạo nhanh hơn khả năng xử lý, công việc chờ sẽ tăng. Một hàng đợi có giới hạn đặt ra sức chứa tối đa cho phần đang chờ và buộc chương trình trả lời câu hỏi: **khi hết chỗ, bên sản xuất phải làm gì?**

Đó là điểm nối giữa cấu trúc dữ liệu và **điều tiết ngược (backpressure)**: trạng thái quá tải ở phía xử lý được phản hồi về phía đưa việc, khiến phía đó chờ, giảm lượng đưa vào hoặc nhận một kết quả từ chối rõ ràng.

Các thuật ngữ trong bài:

- **Sức chứa (capacity):** số phần tử tối đa có thể nằm trong bộ đệm hàng đợi theo hợp đồng lớp.
- **Công việc chờ:** phần tử đã được nhận vào nhưng chưa bị lấy ra.
- **Công việc đang xử lý:** phần tử đã rời hàng đợi nhưng tác dụng xử lý chưa hoàn tất.
- **Tiếp nhận thành công:** thao tác đưa vào hoặc bàn giao đã thành công; khác với xử lý thành công.
- **Chính sách quá tải:** cách ứng dụng phản ứng khi không thể nhận thêm ngay.
- **Ngân sách chờ:** khoảng thời gian hoặc giới hạn tổng mà một yêu cầu được phép dành cho việc tiếp nhận.

Bài học dùng `BlockingQueue` và các triển khai có trong Java 17. Đích chính là hiểu hợp đồng dữ liệu, điều kiện chờ và cách truyền tín hiệu về bên sản xuất, không chỉ chọn một con số capacity.

## 1. Hàng đợi là bộ đệm, không tự làm bên tiêu thụ nhanh hơn

Có thể hình dung một luồng xử lý như sau:

~~~text
Bên sản xuất -> tiếp nhận -> [hàng đợi có sức chứa C] -> bên tiêu thụ -> hoàn tất
~~~

Một chỗ trống được giải phóng khi bên tiêu thụ **lấy phần tử ra**, chưa nhất thiết khi xử lý xong phần tử đó.

Nếu bên sản xuất tạo trung bình `120` việc mỗi giây còn bên tiêu thụ hoàn tất được khoảng `100` việc mỗi giây, phần chờ có xu hướng tăng. Một bộ đệm lớn chỉ kéo dài thời gian trước khi đầy; nó không giải quyết chênh lệch lâu dài.

Trong mô hình đơn giản coi tốc độ đều, bỏ qua các chi tiết khởi động và dao động, bộ đệm trống `200` chỗ có thể hấp thụ khoảng `10` giây chênh lệch `20` việc mỗi giây. Đây là phép tính để hiểu xu hướng, không phải cam kết thời điểm đầy của hệ thống thực.

Hàng đợi có giới hạn giúp ứng dụng đưa quyết định quá tải ra sớm hơn, thay vì để lượng công việc chưa xử lý tăng đến khi bộ nhớ hoặc độ trễ vượt khả năng chịu đựng.

### 1.1. Có giới hạn chưa đủ để tạo backpressure đúng

Nếu hàng đợi đầy nhưng chương trình bỏ qua kết quả thất bại rồi tiếp tục tạo việc như cũ, tín hiệu chưa được truyền về nguồn sản xuất.

Các phản ứng khác nhau có ý nghĩa khác nhau:

- Chờ chỗ trống làm luồng đưa việc chậm lại.
- Trả lỗi hoặc từ chối cho bên gọi có thể làm tầng trước giảm tốc.
- Bỏ việc là chính sách mất dữ liệu có chủ đích, nếu yêu cầu cho phép.
- Đẩy việc sang một danh sách không giới hạn chỉ chuyển nơi tích lũy.

Vì vậy, capacity là một thành phần; chính sách của bên gọi mới hoàn thiện cơ chế điều tiết.

### 1.2. Không phải bộ giới hạn số yêu cầu mỗi giây

Hàng đợi sức chứa `C` có thể nhận một đợt lớn khi đang trống, rồi chặn/từ chối khi đầy. Nó giới hạn phần chờ, không tự bảo đảm một tốc độ cố định như “tối đa 50 yêu cầu mỗi giây”.

Nếu cần quy tắc theo thời gian, phải có cơ chế điều tiết tốc độ riêng. Hàng đợi có thể kết hợp với cơ chế đó, nhưng hai công cụ trả lời hai câu hỏi khác nhau.

## 2. Bốn cách đưa vào khi đang đầy

`BlockingQueue` cung cấp bốn nhóm API để ứng dụng chọn cách phản ứng khi thao tác chưa thể thực hiện ngay. [Java 17: BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)

| Cách đưa vào | Nếu nhận được | Nếu hàng đợi đầy |
|---|---|---|
| `add(item)` | Trả `true`. | Ném `IllegalStateException` do hết sức chứa. |
| `offer(item)` | Trả `true`. | Trả `false` ngay theo cơ chế không đợi chỗ trống. |
| `put(item)` | Kết thúc bình thường. | Chờ cho đến khi có chỗ hoặc bị ngắt. |
| `offer(item, timeout, unit)` | Trả `true`. | Chờ có giới hạn; trả `false` nếu hết thời gian mà chưa nhận được. |

Những kết quả này là một phần giao thức, không phải chi tiết có thể bỏ qua.

Ví dụ minh họa trong một phương thức:

~~~java
java.util.concurrent.BlockingQueue<String> pending =
        new java.util.concurrent.ArrayBlockingQueue<>(128);

boolean accepted = pending.offer("task");
if (!accepted) {
    // Bên gọi phải nhận biết lần tiếp nhận này đã bị từ chối.
}
~~~

Đoạn trên chưa chọn một chính sách nghiệp vụ cụ thể. Trong mã thật, nhánh từ chối phải được biến thành hành vi có ý nghĩa: báo cho bên gọi, chờ theo ngân sách, gộp thay đổi, hoặc bỏ việc có ghi nhận nếu được phép.

### 2.1. offer không chặn để chờ sức chứa

`offer(item)` hữu ích khi bên sản xuất không được phép đợi chỗ trống. Ví dụ một luồng tiếp nhận có thể cần trả kết quả quá tải ngay cho tầng trước.

Nếu gọi `offer` rồi không kiểm tra `boolean`, công việc bị từ chối có thể biến mất mà bên gọi vẫn nghĩ đã nhận thành công.

Không dùng vòng lặp bận như sau để né việc chọn chính sách:

~~~java
while (!pending.offer("task")) {
    // Thử lại liên tục.
}
~~~

Đây là mẫu minh họa không phù hợp cho việc chờ. Nó có thể tiêu tốn CPU, tranh chấp với bên tiêu thụ và không có hạn dừng. Nếu được phép chờ, API chờ đã biểu đạt điều đó rõ hơn.

### 2.2. put tạo phản hồi qua thời gian chờ của luồng

`put` không từ chối chỉ vì hàng đợi đang đầy; nó có thể phải chờ. Nếu bên tiêu thụ không còn tiến triển và không có hủy, một lần chờ có thể không kết thúc.

Điều tiết qua `put` có tác dụng khi việc làm chậm chính luồng sản xuất là phù hợp và tầng trước thực sự nhận được ảnh hưởng đó. Nếu mỗi yêu cầu lại tạo một luồng mới chỉ để đứng chờ `put`, ứng dụng có thể hết tài nguyên luồng hoặc giữ quá nhiều đối tượng chờ bên ngoài hàng đợi.

### 2.3. Timed offer giới hạn một lần tiếp nhận

Ví dụ:

~~~java
boolean accepted = pending.offer("task", 200,
        java.util.concurrent.TimeUnit.MILLISECONDS);
~~~

Đoạn minh họa nằm trong phương thức có xử lý hoặc khai báo `InterruptedException`. Kết quả `false` cần được xử lý như một lần chưa được nhận, không như một việc đang được xử lý ngầm ở hàng đợi.

Thời hạn của API không phải lời hứa thời gian thực rằng luồng chắc chắn quay lại đúng sau `200` mili giây theo đồng hồ ngoài. Lịch chạy của hệ điều hành và tranh chấp có thể ảnh hưởng lúc luồng được chạy tiếp. Không kiểm thử bằng yêu cầu số mili giây thực tế phải bằng chính xác một hằng số.

Nếu thử lại nhiều lần, mỗi lần cho `200` mili giây có thể cộng thành một thời gian rất dài. Khi yêu cầu có ngân sách tổng, cần theo dõi phần thời gian còn lại thay vì đặt lại toàn bộ thời hạn ở mỗi lần thử. `System.nanoTime` được thiết kế để đo thời gian trôi qua trong JVM, không dùng làm ngày giờ lịch. [Java 17: System.nanoTime](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html#nanoTime())

### 2.4. add phù hợp khi đầy được xem là lỗi tại ranh giới gọi

`add` có thể hữu ích khi hợp đồng của đoạn mã coi việc đầy là lỗi cần báo bằng ngoại lệ. Nhưng trong một đường tiếp nhận mà quá tải là kết quả dự kiến, `offer` thường giúp thể hiện nhánh được nhận/từ chối trực tiếp.

Việc đổi `add` thành `put` không chỉ là đổi cú pháp xử lý lỗi: nó thay đổi khả năng chặn luồng và yêu cầu về hủy/dừng.

## 3. Lấy ra và ý nghĩa của hoàn tất

Nhóm lấy phần tử có hình dạng tương ứng:

| Cách lấy | Khi có phần tử | Khi đang rỗng |
|---|---|---|
| `remove()` không đối số | Lấy và xóa phần tử đầu. | Ném `NoSuchElementException`. |
| `poll()` | Lấy và xóa phần tử đầu. | Trả `null`. |
| `take()` | Lấy và xóa phần tử đầu. | Chờ phần tử hoặc bị ngắt. |
| `poll(timeout, unit)` | Lấy phần tử nếu có trong thời gian chờ. | Trả `null` khi hết thời gian chờ mà chưa có. |

`BlockingQueue` không chấp nhận phần tử `null`, nên `null` có thể được dùng làm kết quả “không lấy được phần tử”. Đừng dùng `null` làm thông điệp kết thúc.

### 3.1. Lấy ra không có nghĩa xử lý xong

Ngay sau `take`, phần tử không còn được tính vào `size`, nhưng bên tiêu thụ có thể đang ghi file, tính toán hoặc gọi hệ thống khác.

Do đó:

- Hàng đợi rỗng chưa chứng minh mọi việc đã xong.
- `put`/`offer` thành công chưa chứng minh bên tiêu thụ đã chạy.
- Ngay cả bàn giao trực tiếp qua `SynchronousQueue` cũng chưa chứng minh công việc được xử lý hoàn tất.

Nếu bên sản xuất cần biết kết quả, dùng một cơ chế phản hồi hoàn tất phù hợp như đối tượng kết quả, future hoặc tín hiệu phối hợp. Hàng đợi chỉ quản lý tiếp nhận và lấy phần tử theo hợp đồng của nó.

### 3.2. Sức chứa thường chỉ giới hạn phần đang chờ

Giả sử có `C` chỗ đợi và `W` bên tiêu thụ, mỗi bên giữ một việc đang xử lý. Tổng công việc đã được nhận nhưng chưa hoàn tất có thể lớn hơn `C`.

Nếu mỗi bên tiêu thụ rút cả lô bằng `drainTo` rồi giữ lô ngoài hàng đợi, phần công việc bên ngoài còn có thể lớn hơn nữa. Muốn giới hạn toàn bộ số việc đang hoạt động, cần tính cả các phần đang được giữ ngoài bộ đệm.

## 4. Chọn loại hàng đợi theo hợp đồng

### 4.1. ArrayBlockingQueue: sức chứa mảng cố định

Ví dụ:

~~~java
java.util.concurrent.BlockingQueue<String> queue =
        new java.util.concurrent.ArrayBlockingQueue<>(64);
~~~

`ArrayBlockingQueue` là bộ đệm có giới hạn dùng mảng, lấy theo FIFO. Sức chứa không thay đổi sau khi tạo; `put` chờ khi đầy và `take` chờ khi rỗng. Có tùy chọn công bằng cho các luồng đang chờ. [Java 17: ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html)

FIFO của phần tử không có nghĩa nhiều bên tiêu thụ hoàn tất công việc theo cùng thứ tự. Hai việc được lấy theo thứ tự có thể có thời gian xử lý khác nhau.

Tùy chọn công bằng liên quan thứ tự cấp quyền truy cập cho các bên đang chờ; nó không bảo đảm lịch chạy hay thời gian hoàn tất nghiệp vụ của từng luồng. Cần đánh đổi với thông lượng theo tải thực.

### 4.2. LinkedBlockingQueue: phải chủ động chọn giới hạn

~~~java
java.util.concurrent.BlockingQueue<String> queue =
        new java.util.concurrent.LinkedBlockingQueue<>(64);
~~~

Lớp này dùng các nút liên kết và có thể được tạo với giới hạn. Nếu dùng constructor không đối số, capacity là `Integer.MAX_VALUE`. Đó là một giới hạn kỹ thuật rất lớn, thường không phải mức bảo vệ bộ nhớ/độ trễ hữu ích cho một ứng dụng. [Java 17: LinkedBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html)

Không suy từ chữ `Blocking` rằng nó nhất thiết sẽ sớm làm chậm bên sản xuất vì hết chỗ. Cần xem capacity thật và đường API đang gọi.

Mảng hay nút liên kết có đặc điểm cấp phát/phối hợp khác nhau. Không chọn chỉ bằng một khẳng định “loại này luôn nhanh hơn”; phải đo cùng tải và cùng yêu cầu.

### 4.3. LinkedBlockingDeque khi cần hai đầu

`LinkedBlockingDeque` có các API ở đầu và cuối, cũng có constructor capacity. Constructor mặc định dùng `Integer.MAX_VALUE`. Chọn nó khi bài toán thực sự cần hai đầu; việc có thêm API không tự cải thiện điều tiết tải. [Java 17: LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html)

Cần quy định rõ bên nào thêm/lấy ở đầu nào để không vô tình làm thay đổi thứ tự công việc.

### 4.4. SynchronousQueue: bàn giao, không có bộ đệm

`SynchronousQueue` không có chỗ chứa nội bộ, kể cả một chỗ. Một lần đưa vào phải gặp một lần lấy tương ứng. `offer` không đợi sẽ thất bại nếu không có bên nhận đang sẵn để nhận; dạng chờ có thể đợi cuộc bàn giao. [Java 17: SynchronousQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SynchronousQueue.html)

Đây là mô hình phối hợp trực tiếp. `size` bằng `0` không có nghĩa không có luồng đang chờ trao hoặc nhận; sức chứa bằng không là đặc tính của mô hình.

Không tạo `ArrayBlockingQueue` capacity `0` để thay mô hình này. Chọn đúng lớp có hợp đồng bàn giao.

## 5. remainingCapacity không phải đặt chỗ

Mẫu sau có một khoảng tranh chấp:

~~~java
if (queue.remainingCapacity() > 0) {
    queue.add(item);
}
~~~

Đây là đoạn minh họa, giả sử các biến đã có. Bên khác có thể chiếm chỗ giữa hai lời gọi; `add` vẫn có thể thất bại.

`ArrayBlockingQueue` ghi rõ không thể luôn dự đoán một lần thêm thành công chỉ bằng `remainingCapacity` vì các luồng khác có thể đang thêm hoặc lấy phần tử. [Java 17: ArrayBlockingQueue.remainingCapacity](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html#remainingCapacity())

Dùng trực tiếp thao tác thể hiện ý định:

- Muốn thử ngay: `offer` và xử lý kết quả.
- Muốn chờ: `put` cùng giao thức hủy.
- Muốn chờ có giới hạn: timed `offer` cùng ngân sách.

`size` và `remainingCapacity` vẫn hữu ích cho giám sát. Chúng không thay thế quyết định tiếp nhận của chính thao tác thêm.

## 6. Chương trình kiểm chứng đầy đủ

Tệp `BoundedQueueFlowDemo.java` dùng API Java 17, đã biên dịch bằng `javac --release 17` và chạy trên OpenJDK Zulu 24.0.2. Đây không phải tuyên bố đã chạy trên JVM 17.

Các tình huống chờ dùng latch để đặt thứ tự có ý nghĩa. Không dùng `Thread.sleep` để suy đoán bên sản xuất đã bị chặn. Các kết quả chỉ được in ở những điểm có thể giải thích bằng trạng thái hàng đợi và tín hiệu phối hợp.

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

public class BoundedQueueFlowDemo {
    record Job(int value, boolean stop) {}

    static void await(CountDownLatch event) throws InterruptedException {
        if (!event.await(5, TimeUnit.SECONDS)) {
            throw new AssertionError("Event did not arrive");
        }
    }

    static void join(Thread thread, AtomicReference<Throwable> error)
            throws InterruptedException {
        thread.join(5000);
        if (thread.isAlive()) {
            thread.interrupt();
            throw new AssertionError("Thread did not terminate");
        }
        if (error.get() != null) {
            throw new AssertionError("Background failure", error.get());
        }
    }

    static Thread start(String name, Runnable action) {
        Thread thread = new Thread(action, name);
        thread.setDaemon(true);
        thread.start();
        return thread;
    }

    public static void main(String[] args) throws Exception {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(2);
        System.out.println("offer-A = " + queue.offer("A"));
        System.out.println("offer-B = " + queue.offer("B"));
        System.out.println("remaining-when-full = " + queue.remainingCapacity());
        System.out.println("offer-C-full = " + queue.offer("C"));
        try {
            queue.add("C");
            throw new AssertionError("add should have failed");
        } catch (IllegalStateException ex) {
            System.out.println("add-C-full = " + ex.getClass().getSimpleName());
        }
        System.out.println("timed-offer-C-full = "
                + queue.offer("C", 10, TimeUnit.MILLISECONDS));
        System.out.println("take-first = " + queue.take());
        System.out.println("offer-C-after-space = " + queue.offer("C"));
        System.out.println("remaining-content = " + new ArrayList<>(queue));
        queue.clear();
        System.out.println("poll-empty = " + queue.poll());
        try {
            queue.offer(null);
            throw new AssertionError("null should have failed");
        } catch (NullPointerException ex) {
            System.out.println("offer-null = " + ex.getClass().getSimpleName());
        }

        BlockingQueue<String> waiting = new ArrayBlockingQueue<>(1);
        waiting.put("first");
        CountDownLatch aboutToPut = new CountDownLatch(1);
        CountDownLatch putReturned = new CountDownLatch(1);
        AtomicReference<Throwable> putError = new AtomicReference<>();
        Thread sender = start("waiting-sender", () -> {
            try {
                aboutToPut.countDown();
                waiting.put("second");
                putReturned.countDown();
            } catch (Throwable ex) {
                putError.set(ex);
            }
        });
        await(aboutToPut);
        System.out.println("put-returned-before-space = "
                + (putReturned.getCount() == 0));
        System.out.println("released-item = " + waiting.take());
        await(putReturned);
        join(sender, putError);
        System.out.println("put-item-after-space = " + waiting.take());

        BlockingQueue<String> cancellable = new ArrayBlockingQueue<>(1);
        cancellable.put("held");
        CountDownLatch cancellationAttempt = new CountDownLatch(1);
        AtomicBoolean interrupted = new AtomicBoolean();
        AtomicBoolean restored = new AtomicBoolean();
        AtomicReference<Throwable> cancelError = new AtomicReference<>();
        Thread cancelledSender = start("cancelled-sender", () -> {
            try {
                cancellationAttempt.countDown();
                cancellable.put("not-admitted");
            } catch (InterruptedException ex) {
                interrupted.set(true);
                Thread.currentThread().interrupt();
                restored.set(Thread.currentThread().isInterrupted());
            } catch (Throwable ex) {
                cancelError.set(ex);
            }
        });
        await(cancellationAttempt);
        cancelledSender.interrupt();
        join(cancelledSender, cancelError);
        System.out.println("put-interrupted = " + interrupted.get());
        System.out.println("interrupt-restored = " + restored.get());
        System.out.println("queue-after-cancel = " + new ArrayList<>(cancellable));

        BlockingQueue<String> inFlight = new ArrayBlockingQueue<>(1);
        inFlight.put("work");
        CountDownLatch taken = new CountDownLatch(1);
        CountDownLatch finishAllowed = new CountDownLatch(1);
        AtomicBoolean completed = new AtomicBoolean();
        AtomicReference<Throwable> processingError = new AtomicReference<>();
        Thread processor = start("in-flight-processor", () -> {
            try {
                inFlight.take();
                taken.countDown();
                await(finishAllowed);
                completed.set(true);
            } catch (Throwable ex) {
                processingError.set(ex);
            }
        });
        try {
            await(taken);
            System.out.println("empty-while-processing = " + inFlight.isEmpty());
            System.out.println("completed-while-empty = " + completed.get());
        } finally {
            finishAllowed.countDown();
        }
        join(processor, processingError);
        System.out.println("completed-after-join = " + completed.get());

        BlockingQueue<Job> jobs = new ArrayBlockingQueue<>(2);
        List<Integer> processed = new ArrayList<>();
        AtomicReference<Throwable> jobError = new AtomicReference<>();
        Thread consumer = start("job-consumer", () -> {
            try {
                for (;;) {
                    Job job = jobs.take();
                    if (job.stop()) {
                        return;
                    }
                    processed.add(job.value());
                }
            } catch (Throwable ex) {
                jobError.set(ex);
            }
        });
        int admitted = 0;
        try {
            for (int value = 1; value <= 6; value++) {
                if (!jobs.offer(new Job(value, false), 5, TimeUnit.SECONDS)) {
                    throw new AssertionError("Admission timed out");
                }
                admitted++;
            }
            if (!jobs.offer(new Job(0, true), 5, TimeUnit.SECONDS)) {
                throw new AssertionError("Stop message timed out");
            }
        } catch (Throwable ex) {
            consumer.interrupt();
            throw ex;
        }
        join(consumer, jobError);
        System.out.println("pipeline-admitted = " + admitted);
        System.out.println("pipeline-processed = " + processed);
        System.out.println("pipeline-sum = "
                + processed.stream().mapToInt(Integer::intValue).sum());

        SynchronousQueue<String> handoff = new SynchronousQueue<>();
        System.out.println("handoff-offer-without-receiver = " + handoff.offer("early"));
        AtomicReference<String> received = new AtomicReference<>();
        AtomicReference<Throwable> handoffError = new AtomicReference<>();
        Thread receiver = start("handoff-receiver", () -> {
            try {
                received.set(handoff.take());
            } catch (Throwable ex) {
                handoffError.set(ex);
            }
        });
        if (!handoff.offer("direct", 5, TimeUnit.SECONDS)) {
            receiver.interrupt();
            throw new AssertionError("Handoff timed out");
        }
        join(receiver, handoffError);
        System.out.println("handoff-received = " + received.get());
        System.out.println("handoff-size = " + handoff.size());
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 BoundedQueueFlowDemo.java
java BoundedQueueFlowDemo
~~~

Stdout đã kiểm chứng:

~~~text
offer-A = true
offer-B = true
remaining-when-full = 0
offer-C-full = false
add-C-full = IllegalStateException
timed-offer-C-full = false
take-first = A
offer-C-after-space = true
remaining-content = [B, C]
poll-empty = null
offer-null = NullPointerException
put-returned-before-space = false
released-item = first
put-item-after-space = second
put-interrupted = true
interrupt-restored = true
queue-after-cancel = [held]
empty-while-processing = true
completed-while-empty = false
completed-after-join = true
pipeline-admitted = 6
pipeline-processed = [1, 2, 3, 4, 5, 6]
pipeline-sum = 21
handoff-offer-without-receiver = false
handoff-received = direct
handoff-size = 0
~~~

Các thời hạn năm giây trong ví dụ là giới hạn chờ để phép kiểm chứng không kẹt vô hạn. Chúng không được đề xuất như thời hạn nghiệp vụ dùng chung cho mọi hệ thống.

## 7. Diễn giải các tình huống

### 7.1. Ba cách xử lý một hàng đợi đầy

Hàng đợi sức chứa `2` nhận `A` và `B`:

~~~text
remaining-when-full = 0
offer-C-full = false
add-C-full = IllegalStateException
timed-offer-C-full = false
~~~

Không có bên tiêu thụ trong giai đoạn này, nên timed offer không thể nhận được chỗ trống trong lúc chờ. Chương trình chỉ kiểm tra kết quả `false`, không kiểm tra số mili giây thực tế phải bằng đúng `10`.

Sau khi `take` lấy `A`, một chỗ được giải phóng. `offer("C")` thành công và thứ tự phần đang đợi là `[B, C]`.

### 7.2. put chưa thể hoàn tất khi chưa có chỗ

Bộ đệm sức chứa `1` đã có `first`. Bên gửi báo sắp gọi `put("second")`. Không có ai lấy phần tử trước khi luồng chính kiểm tra tín hiệu hoàn tất, nên:

~~~text
put-returned-before-space = false
~~~

Latch `aboutToPut` đánh dấu đã đi đến đoạn thử đưa vào; nó không phải công cụ đọc trạng thái nội bộ `WAITING` của luồng. Kết luận cần dùng là: khi chỗ duy nhất còn bị `first` chiếm và chưa có bên lấy, lần `put("second")` không thể hoàn tất thành công.

Luồng chính lấy `first`, sau đó chờ `put` trả về và lấy được `second`. Đây là phản hồi qua sức chứa: bên sản xuất chỉ tiến qua lần đưa vào khi phía nhận đã làm xuất hiện chỗ trống.

### 7.3. Hủy một lần chờ

Bộ đệm khác đã chứa `held`, không có bên lấy. Luồng gửi bị ngắt trong hoặc trước đoạn chờ `put` và xử lý `InterruptedException`:

~~~text
put-interrupted = true
interrupt-restored = true
queue-after-cancel = [held]
~~~

Đối tượng `not-admitted` không được nhận trong tình huống này. Nhánh bắt lỗi khôi phục cờ ngắt rồi thoát tác vụ. Nó không coi hủy là lý do để thử đưa lại mãi.

Nếu phương thức đang dùng có thể khai báo `throws InterruptedException`, việc truyền lỗi lên bên gọi cũng là một lựa chọn phù hợp. Nếu đang ở ranh giới không truyền được lỗi ấy, cần giữ và xử lý tín hiệu hủy theo giao thức của tác vụ. [Java 17: Thread.interrupt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#interrupt())

### 7.4. Rỗng nhưng chưa hoàn tất

Bên tiêu thụ lấy `work` ra rồi đợi một tín hiệu cho phép hoàn thành. Trong khoảng đó:

~~~text
empty-while-processing = true
completed-while-empty = false
~~~

Chỉ sau khi được phép đi tiếp và luồng kết thúc, cờ hoàn tất mới là `true`. `isEmpty` quan sát phần đang chờ, không theo dõi phần đã được lấy để xử lý.

### 7.5. Một pipeline có điểm kết thúc rõ

Phần `jobs` có một bên sản xuất và một bên tiêu thụ, sức chứa `2`. Bên sản xuất đưa các giá trị `1..6` bằng timed offer và chỉ tăng số đã nhận sau khi lời gọi thành công.

Thông điệp dừng là một `Job` có trường `stop=true`, được đưa sau toàn bộ công việc thường. Consumer xử lý FIFO và dừng khi lấy thông điệp ấy. Luồng chính `join` trước khi đọc danh sách kết quả:

~~~text
pipeline-admitted = 6
pipeline-processed = [1, 2, 3, 4, 5, 6]
pipeline-sum = 21
~~~

Danh sách `processed` chỉ được consumer sửa trong giai đoạn xử lý. Luồng chính đọc nó sau khi consumer kết thúc, nên không có các luồng cùng ghi một `ArrayList`.

Ví dụ đồng thời kiểm tra số tiếp nhận và kết quả hoàn tất, thay vì chỉ nhìn queue rỗng.

### 7.6. Bàn giao không cần chỗ chứa

`offer("early")` trên SynchronousQueue không có receiver trả `false`. Lần timed offer sau gặp receiver đang hoặc sắp `take`, bàn giao được `direct`:

~~~text
handoff-received = direct
handoff-size = 0
~~~

Queue vẫn không có bộ đệm. Việc bàn giao thành công chỉ xác nhận phía nhận đã nhận đối tượng theo hợp đồng, chưa phải một xác nhận xử lý nghiệp vụ hoàn tất.

## 8. Chính sách quá tải là một phần của yêu cầu

| Chính sách | Khi phù hợp | Điều bên gọi cần biết |
|---|---|---|
| Chờ chỗ trống | Có thể làm chậm luồng sản xuất và vẫn có đường hủy. | Có thể chưa tiến triển nếu phía tiêu thụ dừng. |
| Chờ trong ngân sách | Yêu cầu chỉ chịu được một độ trễ tiếp nhận nhất định. | Hết ngân sách nghĩa là chưa nhận; cần phản hồi rõ. |
| Từ chối ngay | Tầng trước có khả năng giảm tốc, thử lại hoặc báo quá tải. | Phải nhận được kết quả từ chối, không báo thành công giả. |
| Bỏ việc có chủ đích | Dữ liệu cho phép mất theo một quy tắc đã định nghĩa. | Phải rõ bỏ mục nào và đo số mục bị bỏ. |
| Gộp các cập nhật thay thế nhau | Chỉ trạng thái mới nhất hoặc một bản tổng hợp có ý nghĩa. | Phải chứng minh việc gộp không mất thông tin cần thiết. |
| Bên gọi tự xử lý | Luồng gọi được phép làm loại công việc đó và chấp nhận thời gian xử lý. | Ngữ cảnh thực thi, độ trễ và xử lý lỗi thay đổi. |

Không có chính sách chung đúng cho mọi loại công việc. Một mẫu đo nhiệt độ mới có thể thay mẫu cũ theo yêu cầu; một lệnh thanh toán không thể bị bỏ âm thầm theo cùng lý do.

### 8.1. Thử lại phải có giới hạn và điều kiện

Khi bị từ chối, thử lại ngay liên tục có thể khuếch đại tải. Nếu dùng thử lại, cần quy định số lần hoặc ngân sách tổng, khoảng giãn phù hợp và điều kiện hủy. Chỉ tiếp tục khi yêu cầu vẫn còn có ý nghĩa.

Đặc biệt, đừng báo đã nhận công việc rồi mới âm thầm chuyển nó qua một cơ chế thử lại không có giới hạn lưu trữ. Khi ấy giới hạn đã bị đưa ra ngoài hàng đợi chính.

### 8.2. Truyền tín hiệu ngược đến nguồn thật

Một luồng trung gian bị chặn không tự khiến một nguồn bên ngoài ngừng phát dữ liệu. Có thể vẫn còn bộ đệm mạng, danh sách trong bộ đọc hoặc tác vụ đang được tạo trước khi chờ.

Muốn backpressure có tác dụng trên cả đường đi, phải chỉ rõ tín hiệu từ chối/chờ đi qua các tầng như thế nào và tầng nào có thể tạm ngừng nhận thêm.

## 9. Chọn sức chứa theo ngân sách bộ nhớ và độ trễ

Sức chứa được đếm bằng **phần tử**, không phải số byte. Một phần tử có thể giữ mảng dữ liệu lớn hoặc tham chiếu đến cả một đồ thị đối tượng.

Khi tính ngân sách, xét:

- Số phần tử đang nằm trong queue.
- Các công việc đã lấy ra nhưng đang xử lý.
- Các lô đã rút khỏi queue.
- Đối tượng mà bên sản xuất tạo trước khi được phép tiếp nhận.
- Các yêu cầu đang đứng chờ hoặc được giữ ở tầng khác.
- Kích thước và thời gian sống của dữ liệu đi kèm.

Tăng capacity thường giúp hấp thụ một đợt tăng ngắn, nhưng có thể làm công việc nằm chờ lâu hơn trước khi bị từ chối hoặc trước khi xử lý. Một bộ đệm rất lớn có thể chuyển vấn đề từ “từ chối sớm” sang “chờ lâu rồi vẫn hết hạn”.

Cách chọn nên bắt đầu từ yêu cầu:

1. Công việc chấp nhận chờ bao lâu trước khi bắt đầu?
2. Hệ thống có bao nhiêu bộ nhớ cho phần chưa xử lý?
3. Đợt tăng tải thường kéo dài bao lâu?
4. Bên tiêu thụ có thể mở rộng thực sự đến đâu?
5. Khi quá tải kéo dài, chính sách nào được phép thực hiện?

Không dùng một con số queue capacity lấy tùy ý rồi xem nó là chứng minh khả năng chịu tải. Đo lưu lượng, độ sâu hàng đợi, thời gian chờ tiếp nhận, thời gian nằm hàng và thời gian xử lý để điều chỉnh theo dữ liệu thực.

## 10. Dừng, hủy và sự cố của consumer

### 10.1. BlockingQueue không có close chung

Giao diện `BlockingQueue` không cung cấp một phép `close` hoặc `shutdown` nội tại dùng chung cho mọi triển khai. Ứng dụng phải định nghĩa việc không còn nhận và không còn xử lý công việc theo giao thức riêng. [Java 17: vòng đời BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)

Trong ví dụ, thông điệp dừng được dùng vì có một producer và một consumer rõ ràng. Không dùng một giá trị nghiệp vụ có thể xuất hiện thật làm dấu dừng mà không có kiểu hoặc trường phân biệt.

### 10.2. Nhiều producer/consumer cần quy tắc chặt hơn

Nếu dùng thông điệp dừng:

- Chỉ phát thông điệp dừng khi các producer thường đã hoàn tất hoặc bị ngăn không đưa thêm.
- Định nghĩa đủ thông điệp hoặc cơ chế chuyển tiếp cho số consumer cần dừng.
- Chính thông điệp dừng cũng phải được tiếp nhận; không bỏ qua `offer` thất bại vì queue đầy.
- Chờ các consumer kết thúc để xác nhận phần đã lấy ra cũng hoàn tất theo quy tắc xử lý.
- Xác định trường hợp consumer lỗi giữa chừng và công việc chưa xử lý sẽ được báo hay khôi phục ra sao.

Một thông điệp dừng lấy ra bởi một consumer không tự làm tất cả consumer khác thức dậy và dừng.

### 10.3. Consumer chết có thể giữ producer chờ

Một producer dùng `put` không biết consumer đã ngừng vì lỗi. Nếu không còn ai lấy mà queue đầy, nó vẫn có thể chờ.

Cần có bên giám sát vòng đời, phản hồi lỗi và cách hủy việc chờ khi đường xử lý không còn tiến triển. Timed offer giúp tạo điểm kiểm tra lại điều kiện sống và ngân sách; nó không tự sửa consumer.

### 10.4. Không chờ trong khi giữ tài nguyên mà consumer cần

Nếu producer giữ một khóa rồi chờ queue có chỗ, trong khi consumer cần đúng khóa đó để xử lý/lấy bước tiếp theo, hai bên có thể không còn tiến triển.

Tình huống tương tự xảy ra nếu mọi luồng của một pool hữu hạn đều đang chạy producer bị chặn, còn các tác vụ consumer lại đang xếp hàng chờ được pool ấy chạy. Hàng đợi đúng hợp đồng vẫn không cứu được một đồ thị phụ thuộc thực thi bị kẹt.

Cần thiết kế nơi chạy producer/consumer và thứ tự giữ tài nguyên phù hợp, không chỉ tăng capacity để trì hoãn sự cố.

## 11. Công bố đối tượng qua hàng đợi

`BlockingQueue` có bảo đảm nhìn thấy dữ liệu: các hành động trước khi đưa đối tượng vào queue xảy ra trước theo quan hệ bộ nhớ đối với các truy cập/lấy ra đối tượng đó ở luồng khác. Điều này hỗ trợ bàn giao đối tượng đã khởi tạo. [Java 17: BlockingQueue memory consistency](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html)

Nó không tự sao chép sâu phần tử và không tự bảo vệ việc producer tiếp tục sửa chính payload sau khi đã đưa vào.

Mẫu thuận lợi là tạo một thông điệp bất biến hoặc bàn giao quyền sửa rõ ràng. Record `Job` trong ví dụ chỉ chứa `int` và `boolean`, nên không có một danh sách hay mảng có thể sửa nằm bên trong để hai bên vô tình cùng thay đổi.

Nếu thông điệp chứa đối tượng có thể sửa, cần quy định ai còn được sửa và khi nào. Tính an toàn của hàng đợi và tính an toàn của dữ liệu được gửi là hai lớp hợp đồng.

## 12. Liên hệ với hàng đợi của ThreadPoolExecutor

Một pool cố định số luồng không đồng nghĩa hàng đợi có giới hạn hữu ích. `Executors.newFixedThreadPool` dùng hàng đợi chia sẻ không giới hạn theo mô tả API, nên lượng tác vụ chờ vẫn có thể tăng dù số luồng thực thi bị cố định. [Java 17: Executors.newFixedThreadPool](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executors.html#newFixedThreadPool(int))

Với `ThreadPoolExecutor` cấu hình trực tiếp, việc tiếp nhận xét số luồng, khả năng đưa vào work queue và giới hạn luồng tối đa; khi không thể nhận, chính sách từ chối tham gia quyết định. Đặt một BlockingQueue có giới hạn không có nghĩa `execute` sẽ tự chuyển thành `put` và chặn đến khi có chỗ. [Java 17: ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)

`CallerRunsPolicy` là một ví dụ làm chậm bên gửi bằng cách chạy tác vụ bị từ chối ngay trên luồng gọi khi executor chưa shutdown. Nhưng khi executor đã shutdown, chính sách này bỏ tác vụ; nó cũng thay đổi ngữ cảnh và thời gian làm việc của luồng gọi. Không chọn nó mà bỏ qua hợp đồng đó. [Java 17: CallerRunsPolicy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.CallerRunsPolicy.html)

Đây là ví dụ cho nguyên tắc chung: phải đọc hợp đồng của **tầng tiếp nhận**, không chỉ của cấu trúc queue nằm bên trong.

## 13. Những lỗi thường gặp

| Cách nghĩ dễ mắc | Điều còn thiếu |
|---|---|
| “Queue bounded nên tôi đã giới hạn toàn bộ bộ nhớ.” | Payload, công việc đang chạy, producer đang chờ và các bộ đệm ngoài queue vẫn giữ dữ liệu. |
| “offer đã được gọi nên tác vụ đã nhận.” | Phải kiểm tra `boolean`. |
| “put thành công nên việc đã xong.” | Chỉ biết đã tiếp nhận; hoàn tất cần phản hồi riêng. |
| “remainingCapacity còn chỗ nên add chắc thành công.” | Quan sát và thêm là hai thời điểm khác nhau. |
| “Queue rỗng nên có thể tắt hệ thống.” | Có thể còn producer và công việc đang xử lý. |
| “LinkedBlockingQueue mặc định sẽ sớm làm chậm producer.” | Capacity mặc định là `Integer.MAX_VALUE`, không phải ngân sách ứng dụng đã chọn. |
| “Thử lại mãi thì không mất việc.” | Có thể không còn ngân sách, không còn khả năng tiến triển hoặc đang giữ tải ngoài queue. |
| “FIFO bảo đảm hoàn tất đúng thứ tự.” | Nhiều consumer có thể hoàn tất khác thứ tự lấy. |
| “Poison object đã gửi một lần là mọi consumer dừng.” | Cần giao thức cho số consumer và điểm dừng của mọi producer. |

Một hàng đợi trong bộ nhớ cũng không tự là kho lưu bền hay cơ chế xử lý đúng một lần qua sự cố tiến trình. Nếu yêu cầu có bảo đảm lưu bền hoặc khôi phục, cần một thành phần sở hữu những bảo đảm ấy.

## 14. Bài tập tự kiểm tra

### Bài 1 — Nhận hay từ chối?

Một hàng đợi sức chứa `2` đang đầy. So sánh `add`, `offer`, `put` và timed `offer`.

**Đáp án:** `add` ném lỗi hết chỗ; `offer` trả `false`; `put` đợi chỗ hoặc bị ngắt; timed `offer` đợi trong thời hạn rồi trả `false` nếu vẫn không nhận được.

### Bài 2 — Sức chứa còn một

Hai producer cùng thấy `remainingCapacity() == 1` rồi cùng `add`. Có bảo đảm cả hai thành công không?

**Đáp án:** Không. Phép quan sát không đặt trước chỗ. Một bên có thể chiếm chỗ trước; hãy dùng kết quả của thao tác tiếp nhận phù hợp.

### Bài 3 — Một nghìn chỗ và tám consumer

Queue sức chứa `1.000` có tám consumer, mỗi consumer đang giữ một việc. Số công việc đã nhận nhưng chưa xong có thể vượt `1.000` không?

**Đáp án:** Có. Sức chứa chỉ giới hạn phần đang nằm trong queue. Công việc đã lấy để xử lý được tính riêng; còn có thể có các lô hoặc dữ liệu chờ ở tầng khác.

### Bài 4 — Rỗng nhưng còn làm

Consumer đã lấy phần tử cuối và đang ghi kết quả. Producer thấy `isEmpty` là `true`. Có thể coi toàn bộ đã hoàn tất không?

**Đáp án:** Không. Cần tín hiệu hoàn tất hoặc chờ consumer tương ứng, đồng thời biết không còn producer sẽ thêm việc mới.

### Bài 5 — Timed offer lặp lại

Mỗi lần offer được chờ một giây, vòng lặp thử lại không giới hạn. Nó có đáp ứng yêu cầu “mỗi yêu cầu chờ tối đa một giây tổng cộng” không?

**Đáp án:** Không. Mỗi lần thử đặt lại một khoảng chờ. Cần ngân sách tổng và quyết định khi hết ngân sách hoặc bị hủy.

### Bài 6 — Không có bộ đệm

Vì sao `SynchronousQueue.size()` là `0` mà `put` vẫn có thể phải chờ?

**Đáp án:** Lớp này bàn giao trực tiếp giữa bên gửi và bên nhận, không lưu phần tử trong bộ đệm. Chờ là đợi cuộc bàn giao phù hợp, không phải đợi ô mảng trống.

### Bài 7 — Thông điệp dừng

Có ba consumer và nhiều producer. Một producer gửi một thông điệp dừng trước khi các producer khác xong. Có những vấn đề gì?

**Đáp án:** Một consumer có thể dừng trong khi vẫn còn việc được thêm; các consumer khác có thể tiếp tục chờ không có tín hiệu dừng. Cần điểm ngừng nhận chung và cách dừng đủ các consumer, đồng thời xử lý việc tiếp nhận thông điệp dừng.

### Bài 8 — Bộ đệm lớn có chữa quá tải kéo dài?

Producer tạo đều nhanh hơn tốc độ xử lý. Tăng queue từ `100` lên `10.000` có làm hệ thống ổn định lâu dài không?

**Đáp án:** Không tự làm được. Nó tăng khả năng hấp thụ tạm thời và lượng việc chờ, nhưng không xóa chênh lệch tốc độ. Cần điều tiết nguồn, tăng năng lực xử lý phù hợp hoặc áp dụng chính sách quá tải được phép.

Một hàng đợi có giới hạn phát huy tác dụng khi sức chứa, cách tiếp nhận, tín hiệu hoàn tất và đường hủy được thiết kế cùng nhau. Khi hết chỗ, hành động của bên sản xuất phải có ý nghĩa rõ đối với nguồn công việc; đó mới là cơ sở của điều tiết tải có thể kiểm chứng.
