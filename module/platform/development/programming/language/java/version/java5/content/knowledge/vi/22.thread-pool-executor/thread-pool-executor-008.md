# AbortPolicy, CallerRunsPolicy và các chính sách loại bỏ

## 1. Khi không thể nhận thêm công việc

Một `ThreadPoolExecutor` có thể không nhận được tác vụ mới khi:

- Các luồng đã đạt giới hạn và hàng đợi không còn chỗ theo cấu hình.
- Executor đã bước vào quá trình shutdown nên không còn tiếp nhận việc mới.

Lúc đó executor gọi một `RejectedExecutionHandler`. Handler quyết định phản ứng: báo lỗi, chạy ngay ở nơi gửi hoặc loại bỏ công việc.

Đây là **chính sách tiếp nhận khi không còn khả năng nhận bình thường**, không phải bộ xử lý lỗi trong thân tác vụ. Một phép tính đã được nhận rồi sau đó ném `IOException` là tình huống khác.

Lựa chọn handler ảnh hưởng đến hợp đồng mà bên gửi nhìn thấy. Không nên chọn chỉ vì muốn “không còn ngoại lệ” trên log.

## 2. So sánh bốn chính sách dựng sẵn

| Chính sách | Khi bão hòa và executor vẫn mở | Khi executor đã shutdown |
|---|---|---|
| `AbortPolicy` | Ném `RejectedExecutionException` | Cũng ném ngoại lệ |
| `CallerRunsPolicy` | Chạy tác vụ ngay trên luồng gọi execute | Bỏ tác vụ |
| `DiscardPolicy` | Bỏ tác vụ mới âm thầm | Bỏ tác vụ |
| `DiscardOldestPolicy` | Lấy bỏ phần tử đầu queue rồi thử nhận tác vụ mới lại | Bỏ tác vụ mới |

“Bỏ” không tự có nghĩa Future được đánh dấu hủy, và “chạy ở bên gửi” không tự có nghĩa mọi tài nguyên đã được giới hạn.

Các handler cùng triển khai giao diện [RejectedExecutionHandler](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/RejectedExecutionHandler.html).

## 3. AbortPolicy: báo thất bại tiếp nhận trực tiếp

Ví dụ cấu hình:

```java
ThreadPoolExecutor executor = new ThreadPoolExecutor(
        2,
        2,
        0, TimeUnit.SECONDS,
        new ArrayBlockingQueue<>(20),
        new ThreadPoolExecutor.AbortPolicy());
```

Đây là đoạn khai báo minh họa; các lớp thuộc `java.util.concurrent`.

Nếu không nhận thêm được:

```java
try {
    executor.execute(task);
} catch (RejectedExecutionException e) {
    reportNotAccepted(task);
}
```

`task` và `reportNotAccepted` thuộc ứng dụng.

Chính sách này làm việc không tiếp nhận trở nên rõ ràng với bên gửi. Nó là handler mặc định của ThreadPoolExecutor nếu constructor không chỉ định handler khác.

### Abort không có nghĩa hủy mọi việc đang chạy

Ngoại lệ ở lần gửi này không tự dừng các tác vụ đã được nhận trước đó. Nó chỉ báo về công việc đang bị từ chối.

Cũng không nên bắt ngoại lệ rồi gửi lại vô hạn ngay lập tức. Nếu hệ thống đang bão hòa, retry không có giới hạn có thể làm tăng tải và tranh chấp.

Ứng dụng cần quyết định phản hồi phù hợp: từ chối yêu cầu, giảm tốc độ gửi, lưu công việc vào cơ chế bền vững đã thiết kế hoặc thử lại có giới hạn.

Với `submit`, nếu đường thực thi gọi handler và handler ném ngoại lệ, lời gọi submit ném ngay; nó không trả về một Future thành công để bên gửi tiếp tục chờ.

Hợp đồng nằm tại [AbortPolicy API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.AbortPolicy.html).

## 4. CallerRunsPolicy: chuyển công việc sang bên gửi

Khi executor chưa shutdown, handler gọi `run()` của tác vụ ngay trên luồng đang gửi.

Lợi ích có thể có: bên gửi phải bỏ thời gian tự làm việc nên khó tiếp tục đẩy công việc tới nhanh như trước. Cách phản hồi này có thể tạo áp lực ngược (backpressure) trong một số mô hình.

Nhưng nó thay đổi điều mà nhiều nơi gọi ngầm giả định: tác vụ không còn chắc chắn chạy trên một luồng trong nhóm.

### Lời gọi gửi có thể trở thành lời gọi chặn lâu

Giả sử luồng xử lý giao diện gọi `submit` một công việc nặng, tin rằng nó sẽ rời khỏi luồng giao diện. Khi pool đầy, CallerRunsPolicy có thể chạy công việc ngay ở đó, làm giao diện đứng.

Tình huống tương tự xảy ra nếu bên gửi là luồng xử lý sự kiện, luồng cần phản hồi nhanh hoặc đang giữ một khóa mà tác vụ cũng phụ thuộc.

Nếu tác vụ đợi một tín hiệu chỉ có thể được gửi **sau khi submit trả về**, việc chuyển sang chạy đồng bộ có thể gây bế tắc. Phải kiểm tra phụ thuộc trước khi dùng chính sách này.

### Maximum chỉ giới hạn luồng trong pool

Nhiều bên gửi có thể đồng thời tự thực hiện các tác vụ bị từ chối. Những luồng ấy nằm ngoài số lượng worker của executor.

Vì vậy, maximum bằng 8 không bảo đảm toàn ứng dụng chỉ có 8 lời gọi cùng chạm tới cơ sở dữ liệu nếu CallerRunsPolicy cho các bên gửi chạy thêm. Nếu cần giới hạn tài nguyên tuyệt đối, phải có cơ chế quản lý số truy cập phù hợp tại tài nguyên đó.

### Sau shutdown thì không chạy ở bên gửi

CallerRunsPolicy bỏ công việc khi executor đã shutdown. Không chọn nó với niềm tin “bằng cách nào cũng chắc chắn chạy”.

Đây là khác biệt quan trọng giữa quá tải và đóng vòng đời. Xem [CallerRunsPolicy API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.CallerRunsPolicy.html).

### execute và submit khác đường báo lỗi tác vụ

Nếu một Runnable gửi qua `execute` được handler chạy trực tiếp và ném RuntimeException, ngoại lệ có thể đi ra trên luồng gửi.

Nếu dùng `submit` tiêu chuẩn, Runnable mà handler nhận thường là một FutureTask bọc công việc. FutureTask ghi nhận lỗi để `get()` báo bằng ExecutionException; việc tự chạy trên bên gửi không làm mất cơ chế kết quả ấy.

Không gộp lỗi thân công việc với ngoại lệ do chính sách từ chối.

## 5. DiscardPolicy: bỏ tác vụ mới mà không báo trực tiếp

DiscardPolicy không làm gì khi handler được gọi; kết quả là công việc bị từ chối không được chạy bởi đường này.

Nó có thể phù hợp với những công việc mà việc mất một lần xử lý đã được cho phép rõ trong thiết kế, chẳng hạn một tín hiệu không thiết yếu có thể bỏ. Nhưng “không thiết yếu” phải là hợp đồng nghiệp vụ, không phải suy đoán vì muốn tránh lỗi.

### Vấn đề với Future

Nếu submit tạo FutureTask, handler âm thầm bỏ nó rồi trở về, submit vẫn có thể trả Future cho nơi gọi. Future đó chưa được chạy và cũng chưa được hủy.

Bên gọi dùng `future.get()` có thể chờ mãi. Không thể kết luận “submit không ném ngoại lệ nên tác vụ chắc chắn sẽ thực hiện”.

Nếu thiết kế thật sự cho phép bỏ việc, cần quy định cách báo trạng thái, số liệu quan sát hoặc hủy đối tượng kết quả phù hợp. DiscardPolicy dựng sẵn không cung cấp những phần ấy.

Hợp đồng hành vi tối thiểu tại [DiscardPolicy API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.DiscardPolicy.html).

## 6. DiscardOldestPolicy: bỏ đầu hàng đợi, thử lại việc mới

Khi executor vẫn mở, chính sách này:

1. Lấy bỏ phần tử ở đầu work queue nếu có.
2. Thử gọi lại execute cho công việc mới.

Với queue FIFO thông thường, phần tử đầu thường là việc chờ lâu nhất. Nhưng tên “oldest” không có nghĩa nó chọn công việc đang chạy lâu nhất hoặc dùng dấu thời gian để tìm trên toàn hệ thống.

Nó không ngắt tác vụ đang chạy để nhường chỗ.

### Công việc đã được nhận có thể bị loại bỏ

Bên gửi của một công việc trước đó có thể đã nhận Future và tin rằng đang đợi kết quả. Khi một công việc mới tới, handler có thể lấy FutureTask của công việc trước ra khỏi queue mà không tự hủy nó.

Future cũ có thể tiếp tục chưa hoàn tất, dù công việc không còn chờ trong executor.

### Phải đọc thứ tự của queue

Nếu queue có thứ tự ưu tiên thay vì FIFO, đầu queue có thể là việc ưu tiên cao nhất, không phải việc gửi lâu nhất. Ghép chính sách theo tên gọi mà không xem queue có thể loại bỏ sai công việc quan trọng.

Không xem việc “bỏ đầu rồi retry” như bảo đảm tác vụ mới luôn được nhận: trạng thái có thể đổi đồng thời và lần thử lại cũng có thể thất bại.

Với queue không có phần tử chờ để bỏ, như SynchronousQueue, không được giả định thao tác bỏ sẽ tạo ra chỗ cho lần thử lại. Chính sách này phải được đánh giá cùng loại queue.

Các lưu ý được mô tả tại [DiscardOldestPolicy API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.DiscardOldestPolicy.html).

## 7. Thí nghiệm Java 17+: quan sát cả bốn chính sách

Mỗi lần thử có:

- Một worker duy nhất bị giữ ở chốt.
- Một Future nằm trong queue một chỗ.
- Một lời gọi submit tiếp theo buộc phải đi qua handler.

Chương trình cố ý quan sát Future của việc bị bỏ, rồi hủy các Future còn dang dở khi kết thúc để không để bên chờ mắc kẹt.

Lưu thành **`RejectionPoliciesDemo.java`**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.RejectedExecutionHandler;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class RejectionPoliciesDemo {
    public static void main(String[] args) throws Exception {
        demonstrate("AbortPolicy",
                new ThreadPoolExecutor.AbortPolicy());
        demonstrate("CallerRunsPolicy",
                new ThreadPoolExecutor.CallerRunsPolicy());
        demonstrate("DiscardPolicy",
                new ThreadPoolExecutor.DiscardPolicy());
        demonstrate("DiscardOldestPolicy",
                new ThreadPoolExecutor.DiscardOldestPolicy());
    }

    private static void demonstrate(
            String name, RejectedExecutionHandler handler)
            throws Exception {
        CountDownLatch release = new CountDownLatch(1);
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                1,
                1,
                0, TimeUnit.SECONDS,
                new ArrayBlockingQueue<>(1),
                handler);

        Future<?> queued = null;
        Future<Boolean> newest = null;
        Thread caller = Thread.currentThread();

        try {
            executor.execute(() -> {
                try {
                    release.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                }
            });

            queued = executor.submit(() -> {
                // Occupies the only queue slot.
            });

            try {
                newest = executor.submit(
                        () -> Thread.currentThread() == caller);

                if (handler instanceof
                        ThreadPoolExecutor.CallerRunsPolicy) {
                    System.out.println(
                            name + ": ran on caller="
                            + newest.get(5, TimeUnit.SECONDS));
                } else if (handler instanceof
                        ThreadPoolExecutor.DiscardPolicy) {
                    System.out.println(
                            name + ": dropped future done="
                            + newest.isDone());
                } else if (handler instanceof
                        ThreadPoolExecutor.DiscardOldestPolicy) {
                    System.out.println(
                            name + ": removed future done="
                            + queued.isDone());

                    release.countDown();
                    boolean ranOnCaller =
                            newest.get(5, TimeUnit.SECONDS);
                    System.out.println(
                            name + ": replacement ran="
                            + !ranOnCaller);
                }
            } catch (RejectedExecutionException e) {
                System.out.println(name + ": submit rejected");
            }
        } finally {
            if (queued != null && !queued.isDone()) {
                queued.cancel(false);
            }
            if (newest != null && !newest.isDone()) {
                newest.cancel(false);
            }

            release.countDown();
            executor.shutdown();
            try {
                if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                    executor.shutdownNow();
                    if (!executor.awaitTermination(
                            5, TimeUnit.SECONDS)) {
                        throw new IllegalStateException(
                                "Executor did not terminate");
                    }
                }
            } catch (InterruptedException e) {
                executor.shutdownNow();
                Thread.currentThread().interrupt();
                throw e;
            }
        }
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 RejectionPoliciesDemo.java
java RejectionPoliciesDemo
```

Stdout chính xác:

```text
AbortPolicy: submit rejected
CallerRunsPolicy: ran on caller=true
DiscardPolicy: dropped future done=false
DiscardOldestPolicy: removed future done=false
DiscardOldestPolicy: replacement ran=true
```

### Giải thích đầu ra

Vì worker chưa được mở chốt nên nó không thể lấy phần tử đã xếp hàng. Lần submit thứ ba chắc chắn không còn chỗ và không thể thêm worker.

- AbortPolicy báo lỗi ngay tại submit.
- CallerRunsPolicy thực thi ngay trên luồng gửi, nên phép so sánh danh tính luồng là true.
- DiscardPolicy bỏ FutureTask mới; Future trả về chưa hoàn tất.
- DiscardOldestPolicy bỏ FutureTask cũ trong queue, nhận FutureTask mới; Future cũ vẫn chưa hoàn tất.
- Sau khi mở chốt, worker thực hiện công việc mới của DiscardOldestPolicy, nên nó chạy ngoài luồng gửi.

Không có dòng nào cần sleep để đoán executor đã đầy. Các timeout dùng để báo lỗi nếu việc chờ không tiến triển. `main` khai báo `throws Exception` để tập trung vào hành vi chính sách; ứng dụng thực cần phản hồi các lỗi không mong đợi theo ngữ cảnh.

Đây là chương trình so sánh hành vi, không phải mẫu chọn discard cho công việc cần kết quả.

## 8. Thông báo mất công việc là một phần của hợp đồng

Nếu mọi công việc đều phải có trạng thái cuối cùng, cần trả lời được:

- Bên gửi biết yêu cầu không được nhận bằng cách nào?
- Công việc đã xếp hàng nhưng sau đó bị bỏ được thông báo ra sao?
- Future phải kết thúc bằng lỗi, hủy hay một kiểu kết quả nghiệp vụ?
- Có cần lưu lại công việc trước khi xác nhận đã tiếp nhận không?
- Công việc bỏ được đếm và giám sát ở đâu?

Chỉ thêm log trong handler chưa chắc giải quyết yêu cầu của nơi đang đợi Future. Nó có thể cần một trạng thái kết thúc lập trình được, không chỉ một dòng log mà không ai đọc.

Ngược lại, hủy một Future không tự gửi phản hồi nghiệp vụ cho mọi bên quan tâm. Cần thiết kế đường phản hồi từ lúc tiếp nhận.

## 9. Khi cần handler tùy biến

Có thể cài `RejectedExecutionHandler` riêng, nhưng phải giữ tính đúng của vòng đời và đối tượng tác vụ.

Các trách nhiệm thường cần xem xét:

1. Phân biệt executor đã đóng với bão hòa tạm thời.
2. Ghi nhận hoặc báo việc không được nhận.
3. Giải quyết Future nếu chính sách bỏ công việc và đối tượng phù hợp.
4. Không retry đệ quy hoặc chờ vô hạn thiếu kiểm soát.
5. Không giả định mọi Runnable chính là lớp nghiệp vụ ban đầu.

Ví dụ CompletionService hoặc một executor tùy biến có thể bọc công việc; `Runnable` tới handler không nhất thiết là đối tượng Future mà người dùng đang giữ. Không ép kiểu hoặc hủy máy móc nếu chưa hiểu đường bọc.

Không tự dùng `executor.getQueue().put(task)` như một cách “không bao giờ mất việc” mà chưa phân tích shutdown, công việc phụ thuộc nhau và nguy cơ luồng trong nhóm cùng chờ một queue đầy. Việc này có thể bỏ qua quy trình tiếp nhận hoặc gây bế tắc.

Nếu yêu cầu là lưu công việc sống qua lần khởi động lại, một queue trong bộ nhớ của ThreadPoolExecutor không đủ để cung cấp cam kết lưu bền.

## 10. Chọn chính sách theo công việc, không chỉ theo lỗi trên log

| Nhu cầu | Hướng cân nhắc |
|---|---|
| Bên gửi cần biết ngay việc chưa được nhận | AbortPolicy và đường xử lý từ chối rõ |
| Bên gửi có thể tự chạy việc, chấp nhận bị chậm và không có phụ thuộc nguy hiểm | Xem xét CallerRunsPolicy |
| Cho phép mất tác vụ mới một cách có chủ đích | DiscardPolicy chỉ khi hợp đồng cho phép và có quan sát phù hợp |
| Muốn ưu tiên việc mới, chấp nhận bỏ việc đang chờ theo thứ tự queue | Đánh giá kỹ DiscardOldestPolicy và trạng thái của công việc bị bỏ |
| Cần mọi việc có kết quả hoặc lưu bền | Thiết kế thêm hợp đồng tiếp nhận, trạng thái và lưu trữ phù hợp |

Không có handler nào tự tăng năng lực của cơ sở dữ liệu hoặc dịch vụ bên ngoài. Nếu đầu vào cao hơn khả năng xử lý trong thời gian dài, phải giảm tải, giới hạn tiếp nhận, thay đổi công việc hoặc tăng năng lực thực.

Retry là công việc mới đối với hệ thống; phải có ngân sách và tính tới khả năng tạo tác động lặp. Không khôi phục tải bằng cách gửi lại vô hạn từ mọi bên gọi.

## 11. Các lỗi thường gặp

- Cho rằng handler chỉ được gọi khi queue đầy, quên trường hợp shutdown.
- Chọn CallerRunsPolicy rồi giả định submit luôn trở về nhanh.
- Xem maximumPoolSize như giới hạn tổng xử lý của cả ứng dụng khi bên gửi cũng chạy việc.
- Gọi get không thời hạn trên Future có thể đã bị discard.
- Hiểu DiscardOldestPolicy là hủy tác vụ đang chạy lâu nhất.
- Ghép chính sách bỏ đầu queue với queue ưu tiên mà không xét thứ tự.
- Đo tỷ lệ thành công chỉ bằng số lần submit không ném lỗi.
- Bắt RejectedExecutionException rồi bỏ qua yêu cầu mà không phản hồi.

Số liệu nên phân biệt **đã tiếp nhận, bị từ chối, bị loại khỏi queue, bắt đầu chạy, hoàn tất thành công và thất bại**. Một con số “submitted” duy nhất không đủ để biết hệ thống có mất công việc hay không.

## 12. Tự kiểm tra

1. AbortPolicy có hủy các tác vụ đang chạy trước đó không?
2. Sau shutdown, CallerRunsPolicy có còn chạy mọi công việc mới trên bên gửi không?
3. Vì sao DiscardPolicy có thể làm Future.get chờ vô hạn?
4. DiscardOldestPolicy có tự đánh dấu Future của phần tử bị lấy khỏi queue là cancelled không?
5. Nếu queue sắp xếp theo ưu tiên, “đầu queue” có chắc là việc gửi lâu nhất không?
6. Khi dùng CallerRunsPolicy, pool maximum bằng 4 có giới hạn cả bốn bên gửi cùng tự chạy thêm việc không?

**Gợi ý:** (1) Không. (2) Không, nó bỏ việc. (3) FutureTask không được chạy hoặc hủy. (4) Không. (5) Không. (6) Không; các bên gửi nằm ngoài số worker của nhóm.

Chính sách từ chối phải làm rõ **ai chạy hoặc bỏ công việc, bên gửi biết gì, và đối tượng kết quả có được giải quyết hay không**.
