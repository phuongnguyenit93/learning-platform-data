# Ảnh hưởng của việc loại bỏ tác vụ đến Future và bên chờ kết quả

## 1. Không còn trong hàng đợi không có nghĩa Future đã hoàn tất

Một tác vụ được loại bỏ khỏi hệ thống thực thi có thể không bao giờ chạy. Nhưng nếu một bên khác đang giữ Future của tác vụ đó, điều gì sẽ làm Future chuyển sang thành công, thất bại hoặc hủy?

Đây là câu hỏi quan trọng khi dùng `ThreadPoolExecutor` với cơ chế giảm tải, xóa tác vụ chờ hoặc dừng gấp. Nếu chỉ bỏ đối tượng công việc mà không hoàn tất tay cầm kết quả, bên gọi có thể chờ mãi ở `get()`.

Cần tách hai lớp trạng thái:

```text
Lớp thực thi: tác vụ còn trong queue / đang chạy / đã bị lấy ra
Lớp kết quả:  Future chưa xong / thành công / thất bại / bị hủy
```

**Thay đổi lớp thực thi không tự bảo đảm lớp kết quả đã chuyển sang trạng thái kết thúc.** Bài xét `ThreadPoolExecutor` và FutureTask thông thường; các lớp bọc hoặc executor tùy biến cần hợp đồng riêng. Kiến thức này còn áp dụng hiện nay, ví dụ tương thích Java 17 trở lên.

## 2. Vì sao submit có thể trả Future cho một công việc bị bỏ?

Trong triển khai mặc định của `AbstractExecutorService`, submit tạo một `RunnableFuture` (thông thường FutureTask), giao đối tượng bọc đó qua execute và trả nó cho nơi gọi. [AbstractExecutorService](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/AbstractExecutorService.html).

Mô hình khái niệm:

```text
Callable/Runnable ban đầu
    → bọc thành RunnableFuture
    → execute(đối tượng bọc)
    → submit trả Future nếu execute không ném lỗi
```

Nếu handler từ chối chỉ bỏ công việc và trả về bình thường, execute cũng có thể trả về bình thường. Submit khi đó trả một Future chưa được thực thi và chưa được đánh dấu hủy.

FutureTask không tự biết rằng không ai sẽ chạy nó nữa chỉ vì nó mất chỗ trong queue. Nó thường chuyển trạng thái qua việc thực thi xong hoặc thao tác hoàn tất/hủy thích hợp. [FutureTask](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/FutureTask.html).

Hệ quả:

- `future.get()` có thể chờ không có giới hạn do nơi gọi đặt.
- `future.get(timeout, unit)` có thể ném TimeoutException, nhưng timeout đó không tự hoàn tất hoặc hủy Future.
- Việc executor đã hết tải hoặc đã kết thúc về sau không tự chứng minh Future bị bỏ đã done.

## 3. Các cách loại bỏ có ảnh hưởng khác nhau

| Cơ chế | Tác động lên công việc | Ảnh hưởng đến Future thông thường |
|---|---|---|
| `AbortPolicy` | Từ chối bằng ngoại lệ tại nơi giao việc | Submit ném RejectedExecutionException, không trả Future cho lần giao đó |
| `DiscardPolicy` | Bỏ tác vụ bị từ chối, không báo lỗi | Có thể trả Future chưa xong nhưng không còn ai chạy |
| `DiscardOldestPolicy` | Bỏ phần tử đầu queue rồi thử giao việc mới, nếu executor còn mở | Future của việc cũ bị bỏ có thể còn chưa xong |
| `CallerRunsPolicy` khi executor đã shutdown | Bỏ việc bị từ chối thay vì chạy trên luồng gọi | Cũng có nguy cơ Future không được hoàn tất |
| `remove(Runnable)` | Cố lấy đúng đối tượng công việc ra khỏi queue | Không tự tương đương cancel Future |
| `shutdownNow()` | Lấy công việc chưa chạy khỏi queue và cố ngắt việc đang chạy | Future của phần chưa chạy có thể cần xử lý/hủy riêng |
| `purge()` | Dọn các công việc Future đã bị hủy khỏi queue | Hướng ngược: Future đã canceled trước, rồi dọn phần tử chờ |

Bảng không có nghĩa mọi Future của mọi executor đều dùng cùng đối tượng trong queue. Khi có lớp bọc tùy biến, phải xác định đúng tay cầm kết quả và đối tượng được loại bỏ. [ThreadPoolExecutor: Rejected tasks và Queue maintenance](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html).

## 4. DiscardPolicy: giảm tải âm thầm có thể làm mất đường báo kết quả

`DiscardPolicy` cố ý không làm gì trong callback từ chối, khiến tác vụ bị bỏ mà nơi giao việc không nhận một ngoại lệ từ handler. [DiscardPolicy](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.DiscardPolicy.html).

Chính sách đó chỉ có thể phù hợp với hợp đồng chấp nhận mất việc và không dựa vào việc mọi tác vụ phải hoàn tất để tiếp tục. Nếu nơi gọi luôn `submit(...).get()`, việc bỏ âm thầm tạo ra mâu thuẫn: người gửi đang chờ một kết quả mà hệ thống đã quyết định không tạo.

Không có stack trace và lời submit trả bình thường không chứng minh công việc đã được nhận để chạy. Cần kiểm tra chính sách tiếp nhận thay vì chỉ nhìn kiểu trả về Future.

### DiscardOldestPolicy có thể làm một người chờ cũ bị bỏ quên

Một tác vụ mới làm queue đầy; handler lấy phần tử đầu queue ra rồi thử gửi tác vụ mới. Người gửi việc cũ có thể đã cầm Future từ trước và đang chờ. Nếu Future cũ không bị hủy hoặc báo kết thúc theo một cơ chế riêng, người đó không biết công việc đã mất cơ hội chạy.

“Oldest” ở đây gắn với phần tử queue được lấy ra theo cơ chế queue; không mặc định là công việc được gửi sớm nhất trong toàn hệ thống. Tác vụ đang chạy không bị bỏ bởi hành động lấy phần tử đầu queue này.

Tài liệu Java chỉ rõ chính sách này ít hữu ích khi có bên chờ kết thúc hoặc khi thất bại phải được ghi nhận; nó đưa ra hướng cân nhắc hủy Future bị loại bỏ. [DiscardOldestPolicy](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.DiscardOldestPolicy.html).

## 5. Chương trình đầy đủ: bỏ việc khác hủy Future

Thí nghiệm thứ nhất giữ một luồng bận và một chỗ queue đầy, rồi gửi thêm công việc với DiscardPolicy. Thí nghiệm thứ hai chủ động giữ FutureTask và lấy nó khỏi queue bằng remove. Cả hai đều dùng get có thời hạn để quan sát an toàn thay vì cố tình chờ vô hạn.

Lưu thành `RemovedTaskFutureDemo.java`:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.FutureTask;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class RemovedTaskFutureDemo {
    public static void main(String[] args) throws Exception {
        discardDemo();
        removeDemo();
    }

    private static void discardDemo() throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<Runnable>(1),
                new ThreadPoolExecutor.DiscardPolicy());
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        Future<Integer> dropped = null;

        try {
            Future<Integer> running = pool.submit(() -> {
                started.countDown();
                release.await();
                return 1;
            });
            requireStarted(started);
            Future<Integer> queued = pool.submit(() -> 2);
            dropped = pool.submit(() -> 3);

            System.out.println("discard returned a Future");
            printTimeout("discard", dropped);
            System.out.println("discard done before cancel: " + dropped.isDone());
            dropped.cancel(false);
            System.out.println("discard cancelled: " + dropped.isCancelled());

            release.countDown();
            int sum = running.get(10, TimeUnit.SECONDS)
                    + queued.get(10, TimeUnit.SECONDS);
            System.out.println("accepted sum: " + sum);
        } finally {
            if (dropped != null) {
                dropped.cancel(false);
            }
            release.countDown();
            close(pool);
        }
    }

    private static void removeDemo() throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 1, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<Runnable>(1));
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        FutureTask<Integer> removed = new FutureTask<>(() -> 20);

        try {
            Future<Integer> running = pool.submit(() -> {
                started.countDown();
                release.await();
                return 10;
            });
            requireStarted(started);
            pool.execute(removed);
            System.out.println("remove succeeded: " + pool.remove(removed));
            printTimeout("remove", removed);
            System.out.println("remove done before cancel: " + removed.isDone());
            removed.cancel(false);
            System.out.println("remove cancelled: " + removed.isCancelled());

            release.countDown();
            System.out.println("remaining result: "
                    + running.get(10, TimeUnit.SECONDS));
        } finally {
            removed.cancel(false);
            release.countDown();
            close(pool);
        }
    }

    private static void printTimeout(String label, Future<?> future)
            throws Exception {
        try {
            future.get(50, TimeUnit.MILLISECONDS);
            throw new AssertionError("Expected TimeoutException");
        } catch (TimeoutException ex) {
            System.out.println(label + " get: timeout");
        }
    }

    private static void requireStarted(CountDownLatch latch)
            throws InterruptedException {
        if (!latch.await(10, TimeUnit.SECONDS)) {
            throw new AssertionError("Blocking task did not start");
        }
    }

    private static void close(ThreadPoolExecutor pool) {
        pool.shutdown();
        try {
            if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                for (Runnable task : pool.shutdownNow()) {
                    if (task instanceof Future<?> future) {
                        future.cancel(false);
                    }
                }
                if (!pool.awaitTermination(10, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Executor did not terminate");
                }
            }
        } catch (InterruptedException ex) {
            for (Runnable task : pool.shutdownNow()) {
                if (task instanceof Future<?> future) {
                    future.cancel(false);
                }
            }
            Thread.currentThread().interrupt();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac --release 17 RemovedTaskFutureDemo.java
java RemovedTaskFutureDemo
```

Stdout khi thí nghiệm hoàn thành bình thường:

```text
discard returned a Future
discard get: timeout
discard done before cancel: false
discard cancelled: true
accepted sum: 3
remove succeeded: true
remove get: timeout
remove done before cancel: false
remove cancelled: true
remaining result: 10
```

### Giải thích các điểm kiểm chứng

Ở phần discard, latch bảo đảm luồng duy nhất vẫn bận; công việc thứ hai chiếm chỗ queue, nên công việc thứ ba bị bỏ. Submit vẫn trả Future do handler không ném lỗi. Future đó chỉ được đánh dấu hủy sau lời cancel chủ động của chương trình.

Ở phần remove, chương trình giữ đúng đối tượng FutureTask được gửi bằng execute. Khi luồng duy nhất còn bị giữ, đối tượng đó nằm trong queue nên remove thành công. Nhưng việc lấy ra không tự thay trạng thái FutureTask; get vẫn timeout đến khi nó được hủy.

Những lời get timeout trong bài dùng để chứng minh trạng thái chưa hoàn tất tại thời điểm quan sát. Chương trình chủ động cancel để không bỏ lại một tay cầm kết quả không thể tiến triển, rồi giải phóng latch và dừng các executor.

## 6. remove, cancel và purge giải quyết ba việc khác nhau

### remove: thay đổi chỗ đứng trong queue

`pool.remove(task)` cố lấy một Runnable đang chờ ra khỏi hàng đợi. Trả true khi phần tử được lấy ra; nếu công việc đã được một luồng lấy để chạy, lời remove có thể trả false. Không dùng remove làm lệnh dừng phần đã chạy.

Nếu gửi bằng submit, queue thường chứa một lớp bọc FutureTask thay cho Runnable/Callable gốc. Vì thế `remove(originalRunnable)` có thể không tìm được phần tử tương ứng. Không đoán đối tượng theo tên hoặc ép kiểu mù; giữ tay cầm và nhận dạng phù hợp nếu thiết kế thực sự cần quản lý tác vụ chờ.

### cancel: thay đổi hợp đồng kết quả và yêu cầu hủy

Hủy Future thông thường làm bên get nhận CancellationException thay vì chờ một kết quả thành công. Nếu công việc còn chưa bắt đầu và hủy thành công, nó không nên được thực hiện. Nếu đã chạy, `cancel(true)` chỉ yêu cầu ngắt khi hỗ trợ; mã cần hợp tác, và tác dụng phụ cũ không tự được hoàn tác.

Hủy không nhất thiết lập tức lấy phần tử khỏi queue của ThreadPoolExecutor thông thường. Một lớp bọc đã canceled có thể còn chờ đến lúc được luồng lấy ra, hoặc được dọn bằng cơ chế phù hợp.

### purge: dọn phần tử đã hủy

`purge()` cố dọn khỏi queue các công việc Future đã hủy để hỗ trợ giải phóng bộ nhớ. Nó không có vai trò đánh dấu hủy những Future vẫn chưa xong mà ứng dụng tự vứt khỏi queue.

Đừng đảo thứ tự ý nghĩa thành “remove/purge trước rồi Future tự biết canceled”. Chính sách kết quả phải được quyết định rõ, không suy từ việc queue nhìn trống hơn.

## 7. Chính sách từ chối nên có đường kết thúc quan sát được

Với yêu cầu mà nơi gọi luôn đợi kết quả, hai hướng thường dễ lập luận hơn bỏ âm thầm:

- Từ chối rõ ngay tại ranh giới giao việc, chẳng hạn RejectedExecutionException, để nơi gọi biết chưa nhận được một lần thực thi.
- Nếu hợp đồng phải trả tay cầm, bảo đảm công việc không được chạy có một trạng thái kết thúc rõ ràng như bị hủy hoặc thất bại có ý nghĩa.

Một handler tối giản có chủ đích hủy đối tượng Future bị từ chối rồi báo lỗi có thể được minh họa như sau; đây không phải cấu hình hoàn chỉnh cho mọi executor/lớp bọc:

```java
RejectedExecutionHandler cancelAndReject = (task, executor) -> {
    if (task instanceof Future<?> future) {
        future.cancel(false);
    }
    throw new RejectedExecutionException("Task was not accepted");
};
```

Đoạn này cần các import trong `java.util.concurrent`. Với submit chuẩn, ngoại lệ làm lời submit không trả Future; bước hủy còn hữu ích nếu FutureTask đã được bên khác giữ từ trước qua execute. Nếu có lớp bọc bên ngoài, đối tượng handler nhận có thể không phải tay cầm mà người dùng giữ; lúc đó cần một chính sách theo dõi rõ ràng hơn.

Không viết handler thử lại đệ quy vô hạn bằng cách gọi execute liên tục trong điều kiện vẫn quá tải. Nếu định bỏ việc cũ để nhận việc mới, cần xử lý cả Future cũ, khả năng cạnh tranh, shutdown và số lần thử. Hủy một Future không tự là quyết định nghiệp vụ đúng nếu công việc có người dùng khác cùng chờ.

## 8. shutdownNow trả công việc cho chủ sở hữu xử lý

`shutdownNow()` cố ngắt việc đang chạy và trả danh sách các Runnable chưa bắt đầu được lấy khỏi queue. Nó không tự là một báo cáo đầy đủ về mọi Future của ứng dụng.

Chủ sở hữu cần quyết định với phần chưa chạy: hủy các tay cầm tương ứng, ghi nhận chưa xử lý hoặc chuyển công việc sang một nơi nhận khác theo chính sách đã định. Trong trường hợp FutureTask thông thường, có thể cancel những đối tượng Future nhận lại, như hàm close trong ví dụ.

Nếu có lớp bọc hoặc cơ chế điều phối khác, danh sách trả về không đủ để đoán mọi đối tượng gốc. Quản lý tập các Future/nhận dạng công việc từ ranh giới giao việc giúp tránh bỏ quên bên chờ khi dừng.

Không dùng shutdownNow trên một executor dùng chung chỉ để giải quyết một Future bị chờ quá hạn. Đó là hành động ảnh hưởng cả nhóm công việc và thuộc quyền sở hữu vòng đời của executor.

## 9. Bên chờ kết quả cần một hợp đồng đầy đủ

Một phía gửi việc đáng tin không chỉ gọi get có thời hạn rồi quên Future. Cần biết sau timeout ai còn chịu trách nhiệm với công việc đó:

1. Nếu công việc vẫn có giá trị, ai nhận kết quả/lỗi về sau?
2. Nếu không còn giá trị, ai có quyền hủy và quan sát việc dọn tài nguyên?
3. Nếu công việc chưa được nhận hoặc đã bị bỏ, nơi gọi sẽ nhận lỗi/trạng thái nào?
4. Có cần ghi nhận nhận dạng công việc để xử lý lặp hoặc tra cứu trạng thái không?

Phân biệt số lượng tác vụ bị từ chối, tác vụ bị loại khỏi queue, Future bị hủy và công việc thành công. Chỉ đo queue giảm không đủ chứng minh hệ thống đã xử lý xong việc. Một hàng đợi trống có thể đi kèm các bên chờ Future chưa bao giờ được hoàn tất.

Việc thử lại cũng phải theo hợp đồng nghiệp vụ. Với công việc chắc chắn chưa chạy trong ví dụ, đường xử lý đơn giản hơn; trong hệ thống có cạnh tranh hoặc timeout sau khi công việc bắt đầu, phải xét tác dụng phụ đã xảy ra và khả năng xử lý lặp an toàn.

## 10. Tự kiểm tra và thực hành

| Ngộ nhận | Cách hiểu đúng |
|---|---|
| Tác vụ bị bỏ thì get tự ném lỗi | Cần một thao tác hoàn tất/hủy; bỏ âm thầm có thể để Future chưa xong |
| Submit trả Future nghĩa việc chắc chắn được chạy | Chính sách từ chối có thể làm điều đó không đúng |
| Remove thành công tương đương cancel | Remove quản lý queue, cancel quản lý trạng thái/yêu cầu hủy |
| Cancel luôn lập tức giải phóng chỗ queue | Phần tử đã hủy có thể còn cần được lấy/dọn |
| Purge hủy mọi công việc không còn muốn chạy | Purge dọn các Future đã canceled trong queue |
| Executor terminated thì mọi Future người dùng giữ đều done | Future bị bỏ không được hoàn tất có thể vẫn chưa done |

Tự kiểm tra:

1. Vì sao Future thứ ba trong discardDemo được trả về nhưng get timeout? **Handler bỏ công việc mà không ném lỗi hoặc đánh dấu hủy FutureTask.**
2. Vì sao removeDemo dùng FutureTask tự giữ thay vì remove Callable gốc? **Queue cần đúng Runnable đã được giao, không phải mặc định đối tượng nghiệp vụ trước lớp bọc.**
3. Có nên thay tất cả get bằng get có thời hạn để coi như đã sửa vấn đề? **Không.** Nó giới hạn bên chờ nhưng chưa giải quyết tay cầm/công việc bị bỏ.
4. Vì sao gọi cancel(false) phù hợp khi đã biết công việc bị lấy khỏi queue và chưa chạy? **Chỉ cần chuyển tay cầm sang trạng thái hủy; không có phần thực thi của nó cần ngắt trong điều kiện đó.**

Thực hành: đổi DiscardPolicy ở ví dụ thành AbortPolicy và xử lý RejectedExecutionException quanh lần submit thứ ba. Dự đoán sự khác biệt giữa “không nhận được Future vì giao việc bị từ chối rõ ràng” và “nhận một Future không tiến triển”. Tiếp theo, thử một handler đánh dấu Future bị từ chối là canceled theo hợp đồng đã chọn; kiểm tra bên get nhận CancellationException thay cho timeout, đồng thời giữ mọi đường dọn executor.
