# invokeAll và chờ một nhóm kết quả

## 1. Khi một kết quả chưa đủ

Một báo cáo tổng hợp cần dữ liệu từ nhiều phần độc lập: số lượng đơn, tổng doanh thu và số khách hàng. Ta muốn gửi các phép tính rồi đợi cả nhóm trước khi tổng hợp.

Nếu tự gọi `submit` nhiều lần, phải giữ danh sách Future và tự viết logic chờ/hủy. `ExecutorService.invokeAll` cung cấp thao tác nhóm: nhận tập `Callable<T>`, thực hiện chúng và chờ tới mốc kết thúc của nhóm.

Nó trả **danh sách Future**, không trả trực tiếp danh sách giá trị. Bởi mỗi tác vụ có thể thành công, thất bại hoặc bị hủy, mã tổng hợp vẫn phải đọc từng kết quả.

Có hai kiểu dùng:

- Không có timeout: chờ tất cả Future kết thúc.
- Có timeout: chờ tất cả kết thúc hoặc hết thời hạn chung; các việc chưa hoàn tất bị hủy.

Bài dùng API Java 17+ vẫn áp dụng trên Java hiện đại. Các thí nghiệm dùng chốt để tạo mốc đồng bộ, tránh đoán theo tốc độ máy.

## 2. Hợp đồng cần hiểu trước khi gọi

Các chữ ký:

```java
<T> List<Future<T>> invokeAll(
        Collection<? extends Callable<T>> tasks)
        throws InterruptedException;

<T> List<Future<T>> invokeAll(
        Collection<? extends Callable<T>> tasks,
        long timeout, TimeUnit unit)
        throws InterruptedException;
```

Đây là chữ ký API, không phải phương thức mà ứng dụng phải tự triển khai.

| Đặc điểm | Không timeout | Có timeout |
| --- | --- | --- |
| Thời điểm trả về bình thường | Khi tất cả Future kết thúc | Khi tất cả kết thúc hoặc hết thời gian chờ |
| Thứ tự danh sách Future | Theo thứ tự duyệt đầu vào | Theo thứ tự duyệt đầu vào |
| Việc chưa xong khi hết hạn | Không có thời hạn tự đặt | Bị hủy |
| Cách nhận lỗi riêng của tác vụ | Gọi `get()` trên Future | Gọi `get()` trên Future chưa bị hủy |
| Luồng gọi bị ngắt khi chờ | Ném `InterruptedException`, hủy việc chưa xong | Tương tự |

Sau khi lời gọi trả về bình thường, mỗi Future trong danh sách có `isDone() == true`. Tuy nhiên, hoàn thành bằng lỗi hoặc hủy cũng được tính là done. [Tài liệu invokeAll](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html#invokeAll(java.util.Collection))

Dùng `List` khi cần ánh xạ kết quả rõ ràng theo vị trí. Không thay đổi collection đầu vào trong lúc `invokeAll` đang hoạt động; kết quả khi sửa đồng thời collection không được hợp đồng xác định.

Nếu bộ thực thi chỉ có hai luồng và nhóm có mười tác vụ, không phải cả mười cùng chạy. Các tác vụ còn lại phải chờ; `invokeAll` không vượt qua giới hạn tài nguyên của bộ thực thi.

## 3. Ví dụ: trả đủ Future dù một tác vụ lỗi

Trong chương trình dưới đây, tác vụ A chờ tín hiệu từ B; tác vụ C ném lỗi. Danh sách đầu vào vẫn có thứ tự A, B, C.

Tệp **InvokeAllResultsDemo.java**:

```java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class InvokeAllResultsDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(3);
        CountDownLatch bReachedSignal = new CountDownLatch(1);

        List<String> labels = List.of("A", "B", "C");
        List<Callable<String>> tasks = List.of(
                () -> {
                    bReachedSignal.await();
                    return "A-result";
                },
                () -> {
                    bReachedSignal.countDown();
                    return "B-result";
                },
                () -> {
                    throw new IllegalArgumentException("C failed");
                }
        );

        try {
            List<Future<String>> futures = pool.invokeAll(tasks);

            System.out.println("futureCount=" + futures.size());
            for (int i = 0; i < futures.size(); i++) {
                Future<String> future = futures.get(i);
                String label = labels.get(i);

                System.out.println(label + ".done=" + future.isDone());
                try {
                    System.out.println(label + ".result=" + future.get());
                } catch (ExecutionException ex) {
                    System.out.println(label + ".failure="
                            + ex.getCause().getClass().getSimpleName());
                } catch (CancellationException ex) {
                    System.out.println(label + ".cancelled=true");
                }
            }

            System.out.println("executorShutdown=" + pool.isShutdown());
        } finally {
            bReachedSignal.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor did not terminate");
            }
        }
    }
}
```

Chạy:

```shell
javac --release 17 InvokeAllResultsDemo.java
java InvokeAllResultsDemo
```

Stdout khi hoàn tất bình thường:

```text
futureCount=3
A.done=true
A.result=A-result
B.done=true
B.result=B-result
C.done=true
C.failure=IllegalArgumentException
executorShutdown=false
```

Cách đọc:

1. Một tác vụ lỗi không làm `invokeAll` tự ném `ExecutionException` của tác vụ đó. Lỗi nằm trong Future tương ứng.
2. A và B vẫn trả kết quả; C được báo lỗi khi gọi `get()`.
3. Duyệt Future theo đầu vào cho kết quả hiển thị A, B, C. Đây không phải bằng chứng thứ tự bắt đầu hay kết thúc.
4. `invokeAll` không đóng bộ thực thi. Bên sở hữu vẫn phải quản lý vòng đời.

Chốt chỉ bảo đảm A chưa thể đi qua điểm chờ trước khi B gửi tín hiệu. Nó không cam kết B đã trả kết quả trước A, vì sau `countDown()`, hai luồng lại có thể chạy theo lịch khác nhau.

## 4. invokeAll không phải cơ chế dừng ngay khi có lỗi

Giả sử tác vụ C lỗi sau 10 ms, còn A chờ một dịch vụ không bao giờ phản hồi. Bản không timeout vẫn có thể chờ A mãi; nó không tự hủy A chỉ vì C đã thất bại.

Cần chọn theo hợp đồng nghiệp vụ:

- Muốn thu thập kết quả của mọi phần độc lập: `invokeAll` phù hợp.
- Muốn phản hồi từng kết quả ngay khi xong: cần cách thu nhận theo thứ tự hoàn thành.
- Muốn một thành công là đủ: cân nhắc `invokeAny`.
- Muốn một lỗi dẫn tới hủy các phần liên quan: phải thiết kế chính sách điều phối riêng.

“Chờ cả nhóm” không tự đồng nghĩa “mọi phần thành công” hay “toàn bộ là một giao dịch”. Nếu một tác vụ đã ghi dữ liệu rồi tác vụ khác lỗi, `invokeAll` không hoàn tác dữ liệu trước đó.

## 5. Timeout là ngân sách chung, gồm cả thời gian chờ hàng đợi

Ví dụ:

```java
List<Future<String>> futures =
        pool.invokeAll(tasks, 2, TimeUnit.SECONDS);
```

Đây là một lời gọi trong phương thức đã có `pool` và `tasks`. Hai giây là ngân sách chờ của **lời gọi nhóm**, không phải hai giây mới được cấp riêng cho từng tác vụ lúc nó bắt đầu.

Khi hết hạn, danh sách vẫn tương ứng với các tác vụ đầu vào. Tác vụ chưa xong bị hủy. Lời gọi này không ném `TimeoutException` chỉ vì thời hạn nhóm hết; kiểm tra các Future để phân biệt kết quả và hủy. [Tài liệu invokeAll có timeout](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html#invokeAll(java.util.Collection,long,java.util.concurrent.TimeUnit))

Nếu lần lượt gọi `get(2, SECONDS)` trên mười Future, bạn có thể cấp nhiều lượt chờ hai giây, làm tổng thời gian khác hẳn một ngân sách hai giây cho nhóm.

Timeout cũng không phải giới hạn cứng cho mọi lệnh trong ứng dụng. Việc chuẩn bị dữ liệu đầu vào, xử lý kết quả, đóng bộ thực thi và dọn tài nguyên cần ngân sách riêng nếu yêu cầu cuối cùng có thời hạn.

## 6. Thí nghiệm: nhóm hết hạn trước khi có luồng rảnh

Để kết quả xác định, chương trình chiếm luồng duy nhất bằng một tác vụ ngoài nhóm. Các tác vụ trong nhóm không thể chạy trước khi bộ chặn được mở. Lời gọi nhóm hết hạn và hủy chúng.

Tệp **InvokeAllTimeoutDemo.java**:

```java
import java.util.List;
import java.util.concurrent.Callable;
import java.util.concurrent.CancellationException;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class InvokeAllTimeoutDemo {
    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        CountDownLatch blockerStarted = new CountDownLatch(1);
        CountDownLatch releaseBlocker = new CountDownLatch(1);
        AtomicInteger groupRuns = new AtomicInteger();

        try {
            Future<?> blocker = pool.submit(() -> {
                blockerStarted.countDown();
                releaseBlocker.await();
                return null;
            });

            if (!blockerStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Blocker did not start");
            }

            List<Callable<Integer>> tasks = List.of(
                    () -> groupRuns.incrementAndGet(),
                    () -> groupRuns.incrementAndGet()
            );

            List<Future<Integer>> futures =
                    pool.invokeAll(tasks, 100, TimeUnit.MILLISECONDS);

            System.out.println("futureCount=" + futures.size());
            for (int i = 0; i < futures.size(); i++) {
                Future<Integer> future = futures.get(i);
                System.out.println("task" + i + ".done=" + future.isDone());
                System.out.println("task" + i + ".cancelled="
                        + future.isCancelled());
                try {
                    future.get();
                } catch (CancellationException ex) {
                    System.out.println("task" + i + ".get=CancellationException");
                }
            }

            releaseBlocker.countDown();
            blocker.get();

            // Moc nay nam sau nhom cong viec trong hang doi mot luong.
            pool.submit(() -> "queue-passed").get();
            System.out.println("groupRuns=" + groupRuns.get());
            System.out.println("executorUsable="
                    + pool.submit(() -> "OK").get());
        } finally {
            releaseBlocker.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor did not terminate");
            }
        }
    }
}
```

Chạy:

```shell
javac --release 17 InvokeAllTimeoutDemo.java
java InvokeAllTimeoutDemo
```

Stdout:

```text
futureCount=2
task0.done=true
task0.cancelled=true
task0.get=CancellationException
task1.done=true
task1.cancelled=true
task1.get=CancellationException
groupRuns=0
executorUsable=OK
```

Tác vụ chưa bắt đầu vẫn tiêu thụ ngân sách nhóm trong lúc chờ hàng đợi. Sau khi mở bộ chặn và đi qua hàng đợi, phần thân nhóm chưa từng tăng `groupRuns`.

Không đo thời gian thực tế rồi khẳng định lời gọi luôn mất đúng 100 ms. Lập lịch và chi phí xử lý có thể làm mốc đo khác đi. Hợp đồng cần hiểu là thời hạn chờ nhóm và chính sách hủy việc chưa hoàn tất.

Trong một nhóm thực tế, một số Future có thể thành công, một số lỗi và số khác bị hủy khi hết hạn. Ví dụ cố ý giữ toàn bộ nhóm chưa chạy để minh họa đường hủy một cách chắc chắn; nó không nói rằng timeout luôn làm mọi Future bị hủy.

## 7. Mã tổng hợp phải giữ danh tính từng phần

Khi nhận danh sách Future, có thể xử lý từng phần theo ba nhánh:

```text
Future[i]
    -> get() trả giá trị: lưu kết quả cho công việc i
    -> ExecutionException: lưu lỗi của công việc i
    -> CancellationException: lưu trạng thái hủy của công việc i
```

Luôn giữ liên hệ với mã phần việc, chẳng hạn `sectionId` hoặc đối tượng đầu vào. Nếu dùng một collection không có thứ tự nghiệp vụ rõ ràng rồi đoán rằng phần tử đầu là “doanh thu”, dữ liệu có thể bị gắn nhầm.

Hợp đồng trả về của báo cáo cũng cần rõ:

- Bắt buộc đủ mọi phần thành công: một phần lỗi/hủy làm báo cáo thất bại.
- Chấp nhận một phần: nêu rõ phần nào thiếu và vì sao.
- Có giá trị dự phòng: biểu diễn nó là dữ liệu dự phòng, không giả vờ là kết quả chính.

Không chỉ kiểm tra `isDone()` rồi sử dụng kết quả như thành công. Việc hủy và kết thúc bằng ngoại lệ đều có trạng thái done. [Tài liệu Future.get và isDone](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/Future.html)

Nếu duyệt danh sách và ném ngay lỗi đầu tiên, bạn có thể bỏ qua việc ghi nhận các lỗi còn lại. Đó có thể là chính sách hợp lệ, nhưng phải chủ động chọn; với báo cáo chẩn đoán, thu thập đầy đủ các kết quả thường hữu ích hơn.

## 8. Ngắt luồng điều phối và giới hạn của việc hủy

Nếu luồng gọi bị ngắt trong lúc `invokeAll` chờ, phương thức ném `InterruptedException`; các tác vụ chưa hoàn tất bị hủy. Vì không trả về bình thường, bạn không nhận danh sách kết quả như trường hợp timeout.

Tầng gọi nên truyền ngoại lệ ngắt hoặc, nếu không truyền tiếp được, khôi phục cờ ngắt và rời luồng xử lý theo chính sách. Đừng bắt rồi tiếp tục như nhóm đã hoàn tất thành công.

Dù do timeout hay ngắt bên điều phối, việc hủy không bảo đảm mã đang chạy đã dừng tức thì. Tác vụ cần hợp tác với ngắt, API I/O cần timeout/cơ chế đóng phù hợp và tài nguyên cần được dọn trong phạm vi đúng.

Không lấy `isCancelled() == true` làm bằng chứng duy nhất để đóng một tài nguyên mà tác vụ có thể vẫn đang sử dụng. Nếu cần xác nhận phần xử lý đã thoát, thiết kế thêm mốc hoàn tất hoặc quản lý vòng đời tài nguyên phù hợp.

## 9. Hai dạng lỗi ở hai thời điểm

`invokeAll` có thể ném `RejectedExecutionException` nếu một tác vụ không thể được lập lịch, chẳng hạn bộ thực thi đã bị đóng theo chính sách từ chối tiêu chuẩn. Đây là lỗi tiếp nhận công việc, khác với lỗi bên trong `Callable`.

Một `Callable` ném `IOException` được quan sát qua `ExecutionException` khi đọc Future tương ứng. Đừng cho rằng bắt `RejectedExecutionException` là đã xử lý mọi lỗi nhóm.

Cũng không xem `invokeAll` là thao tác gửi nguyên tử kiểu “hoặc nhận hết hoặc không nhận gì”. Nếu xảy ra lỗi trong quá trình lập lịch, một số công việc có thể đã được gửi/chạy và tạo tác dụng phụ. Hệ thống cần thiết kế công việc và chính sách lỗi phù hợp, thay vì giả định có giao dịch bao quanh nhóm.

Collection hoặc phần tử null cũng không phải đầu vào hợp lệ. Dùng một danh sách đã xác định và tránh sửa nó khi đang gọi giúp làm rõ phạm vi nhóm.

## 10. Khi cần kết quả ngay lúc từng tác vụ xong

`invokeAll` là một điểm chờ cả nhóm. Nếu cần hiển thị kết quả sớm của tác vụ nhanh trong khi tác vụ khác còn chạy, `ExecutorCompletionService` cho phép gửi công việc và lấy Future đã hoàn thành từ hàng đợi bằng `take()` hoặc `poll()`.

Khác biệt cần nhớ:

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Chờ cả nhóm và ghép theo đầu vào | `invokeAll` |
| Xử lý từng kết quả khi nó hoàn tất | `ExecutorCompletionService` |
| Chỉ cần một tác vụ thành công | `invokeAny` |

Đây là lựa chọn theo cách thu nhận kết quả, không phải bảng xếp hạng tốc độ. Với CompletionService, vẫn cần tự giữ handle để hủy, xử lý lỗi và quản lý thời hạn của toàn nhóm. [Tài liệu ExecutorCompletionService](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorCompletionService.html)

## 11. Tránh chờ nhóm trên chính bộ luồng đang cạn vị trí

Nếu một tác vụ trên bộ thực thi một luồng gọi `invokeAll` cho các tác vụ con trên cùng bộ thực thi rồi chờ, nó đang giữ vị trí duy nhất mà các tác vụ con cần để chạy.

Với bộ nhiều luồng, tình huống vẫn có thể xảy ra khi mọi luồng đều bị các tác vụ cha giữ để chờ con. Tăng số luồng không tự giải quyết quan hệ chờ.

Đặt điều phối ở ngoài bộ thực thi công việc, làm phép tính con trực tiếp khi thích hợp hoặc thiết kế quan hệ phụ thuộc khác. Bản có timeout có thể giải phóng việc chờ khi hết hạn, nhưng không biến thiết kế thiếu vị trí thành cách thực thi hiệu quả.

## 12. Tự kiểm tra trước khi dùng invokeAll

Một nhóm tạo báo cáo gồm 20 phần, bộ thực thi có 4 luồng và thời hạn nhóm là 3 giây. Hãy giải thích:

1. Bao nhiêu phần có thể được thực hiện cùng lúc?
2. Phần còn trong hàng đợi có được cấp thêm 3 giây lúc bắt đầu không?
3. Sau khi lời gọi trả về, làm sao biết phần nào thành công?
4. Một phần lỗi có tự dừng các phần khác không?
5. Khi có Future bị hủy, ai xác nhận tác vụ đã dọn tài nguyên?
6. Kết quả báo cáo có chấp nhận thiếu một phần không?

Chỉ khi trả lời rõ các câu này, lời gọi chờ nhóm mới gắn được với hợp đồng nghiệp vụ: đủ kết quả nào, trong thời gian nào và xử lý phần việc chưa hoàn tất ra sao.
