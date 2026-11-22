# SubmissionPublisher và executor sử dụng trong Java Flow

`SubmissionPublisher<T>` là một triển khai có sẵn của `Flow.Publisher<T>` trong `java.util.concurrent` từ Java 9. Nó nhận phần tử từ producer và **phát bất đồng bộ** các tín hiệu đến subscriber bằng một `Executor`. Đây là điểm then chốt: **luồng gọi `submit()` không nhất thiết là luồng chạy `Subscriber.onNext()`**. Executor quyết định nơi thực thi việc giao tín hiệu; yêu cầu `Subscription.request(n)` và buffer theo từng subscriber quyết định tốc độ có thể tiếp nhận.

Bài này tập trung vào **Java concurrency nói chung**, không phụ thuộc Spring. Ta sẽ học cách chọn executor, phân biệt buffer với demand, nhận biết lúc `submit()` bị chặn, dùng `offer()` có chính sách drop, quản lý lỗi và đóng tài nguyên. Ví dụ chạy được trên JDK 21+ nhưng cơ chế `Flow` và `SubmissionPublisher` đã có từ Java 9.

## 1. Từ Flow đến SubmissionPublisher

Bốn giao diện chính của `java.util.concurrent.Flow`:

| Vai trò | Giao diện | Trách nhiệm |
|---|---|---|
| Nguồn dữ liệu | `Flow.Publisher<T>` | Đăng ký subscriber; phát `onSubscribe`, `onNext`, `onError`, `onComplete` theo protocol |
| Bên nhận | `Flow.Subscriber<T>` | Nhận subscription, xử lý phần tử, nhận tín hiệu kết thúc/lỗi |
| Kênh điều phối | `Flow.Subscription` | `request(n)` yêu cầu thêm `n` item, `cancel()` ngừng subscription |
| Vừa nhận vừa phát | `Flow.Processor<T,R>` | Vừa là subscriber vừa là publisher, dùng khi xây pipeline xử lý |

`SubmissionPublisher<T>` thực thi `Flow.Publisher<T>` và `AutoCloseable`. Nó cung cấp sẵn logic đăng ký, buffer, dispatch bất đồng bộ và xử lý thiếu dung lượng. Khi gọi `submit(item)`, producer giao item cho publisher; executor được dùng để chạy việc **gửi tín hiệu** đến subscribers (ví dụ callback `onNext`), không phải tự động biến công đoạn tạo item của producer thành một task trên executor.

~~~text
                 PRODUCER THREAD
                      |
                submit(item)
                      |
             SubmissionPublisher
                      |
       +--------------+---------------+
       |                              |
    buffer S1                      buffer S2
       |                              |
request(2) của S1              request(1) của S2
       |                              |
       +----------- executor ---------+
                    |
         dispatch onNext(item)
             (async callbacks)
~~~

Mỗi subscriber có **buffer riêng**, được mở rộng khi cần đến mức capacity được cấu hình. Một subscriber có thể chậm hoặc thiếu demand trong khi subscriber khác xử lý nhanh. Nếu không có drop hoặc exception, mỗi subscriber hiện tại nhận các item mới theo đúng thứ tự đã được gửi cho subscription đó; không có cam kết tổng thứ tự thời gian giữa các subscriber.

Những nguyên tắc khác:

- `onSubscribe(subscription)` là tín hiệu thiết lập subscription. Subscriber gọi `subscription.request(n)` với **`n > 0`** để nhận đến `n` phần tử; `request(0)` hoặc âm là yêu cầu không hợp lệ, dẫn đến `onError`.
- `onNext` chỉ được phát khi có demand đã yêu cầu; các item chưa phát được giữ trong buffer nếu còn chỗ.
- `onComplete` là kết thúc bình thường; `onError` là kết thúc thất bại; một subscription không được nhận cả hai tín hiệu terminal.
- `cancel()` của một subscriber không phải `close()` toàn bộ publisher và không tự động hủy subscription của người khác.
- `submit(null)` không hợp lệ và gây `NullPointerException`.

## 2. Executor mặc định và executor tự cấu hình

Các constructor quan trọng:

~~~java
// Executor mặc định + dung lượng mặc định.
SubmissionPublisher<String> a = new SubmissionPublisher<>();

// Tự cấp executor và mức buffer tối đa cho mỗi subscriber.
SubmissionPublisher<String> b =
        new SubmissionPublisher<>(executor, maxBufferCapacity);

// Có thêm callback xử lý lỗi do onNext của subscriber ném ra.
SubmissionPublisher<String> c =
        new SubmissionPublisher<>(executor, maxBufferCapacity, onNextErrorHandler);
~~~

Đây là **đoạn minh họa API**, không phải chương trình độc lập; `executor`, `maxBufferCapacity` và `onNextErrorHandler` là các biến phải khai báo trước.

**Mặc định**, `new SubmissionPublisher<>()` dùng `ForkJoinPool.commonPool()` nếu pool hỗ trợ parallelism ít nhất 2; nếu không, implementation tạo một thread mới cho mỗi task giao tín hiệu. Dung lượng buffer mặc định là `Flow.defaultBufferSize()`. Vì vậy không nên khẳng định rằng mọi máy, mọi cấu hình đều chắc chắn chạy callback trên `commonPool`.

**Tự cấu hình** bằng `new SubmissionPublisher<>(executor, capacity)` có các lợi ích:

- Kiểm soát thread dùng cho subscriber callbacks, tên thread, số platform workers, chính sách shutdown và tài nguyên.
- Cách ly workload giao dữ liệu khỏi các công việc không liên quan trên `commonPool`.
- Lựa chọn `newFixedThreadPool(n)` khi có số lượng subscribers tương đối dự đoán được và công việc giao tín hiệu phù hợp.
- Có thể sử dụng `Executors.newVirtualThreadPerTaskExecutor()` (Java 21+) khi callbacks cần chờ I/O, nhưng vẫn phải giới hạn tải, tài nguyên downstream và số task outstanding. Virtual threads không tự giải quyết buffer saturation hay slow subscriber.

`executor` ở đây nhận các **tác vụ dispatch nội bộ của publisher**; không nên hiểu “mỗi item luôn tạo một thread mới”. Một delivery task có thể xử lý nhiều item, chi tiết lập lịch phụ thuộc implementation. `getExecutor()` trả executor đang dùng; `getMaxBufferCapacity()` trả mức capacity thực tế. Capacity là **theo từng subscriber**, và implementation có thể làm tròn capacity yêu cầu lên lũy thừa 2 hoặc chặn ở giới hạn hỗ trợ: hãy kiểm tra giá trị trả về thay vì giả định luôn đúng literal đưa vào constructor.

## 3. Ví dụ đầy đủ: FixedThreadPool giao tín hiệu

Tạo file **`SubmissionExecutorDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class SubmissionExecutorDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch completed = new CountDownLatch(1);

        try (ExecutorService delivery = Executors.newFixedThreadPool(2);
             SubmissionPublisher<String> publisher =
                     new SubmissionPublisher<>(delivery, 8)) {

            publisher.subscribe(new Flow.Subscriber<String>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription s) {
                    subscription = s;
                    subscription.request(1);
                }

                @Override
                public void onNext(String item) {
                    System.out.println("received=" + item
                            + " virtual=" + Thread.currentThread().isVirtual());
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable error) {
                    System.out.println("error=" + error.getClass().getSimpleName());
                    completed.countDown();
                }

                @Override
                public void onComplete() {
                    System.out.println("complete");
                    completed.countDown();
                }
            });

            publisher.submit("A");
            publisher.submit("B");
            publisher.close();

            if (!completed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Subscriber did not complete");
            }
        }
    }
}
~~~

Chạy với JDK 21+:

~~~bash
javac SubmissionExecutorDemo.java
java SubmissionExecutorDemo
~~~

Stdout thành công:

~~~text
received=A virtual=false
received=B virtual=false
complete
~~~

Giải thích:

1. `newFixedThreadPool(2)` tạo tối đa hai **platform worker threads**; `onNext` chạy trên worker của executor nên `Thread.currentThread().isVirtual()` là `false`.
2. `onSubscribe` lưu `Subscription` và yêu cầu một item. Sau mỗi `onNext`, subscriber yêu cầu thêm một item. Đây là mô hình **request từng phần tử**.
3. `submit("A")` và `submit("B")` đưa item vào publisher; callback được gọi **bất đồng bộ**. Publisher giữ thứ tự hai item cho cùng subscription.
4. `close()` phát yêu cầu kết thúc bình thường và không nhận thêm item mới; nó **không đồng nghĩa subscriber đã xử lý xong callback terminal trước khi `close()` trả về**. Ta dùng `CountDownLatch` để đợi `onComplete`/`onError`.
5. `try-with-resources` đóng publisher và executor theo thứ tự ngược lúc kết thúc. Sau khi đóng publisher, executor vẫn cần được đóng riêng vì **SubmissionPublisher không sở hữu quyền tự shutdown executor mà caller đã cấp**.
6. Trong đường chạy bình thường, `onError` không được gọi. Nếu callback xảy ra lỗi, đường đi khác có thể in thông báo lỗi hoặc phải được xử lý riêng.

Ví dụ dùng hai worker để thấy rõ việc lựa chọn executor; **không có cam kết mỗi subscriber luôn được gán cố định một thread**, cũng không cam kết hai item được xử lý trên hai thread khác nhau.

## 4. Backpressure là demand, buffer không phải giấy phép gửi vô hạn

Trong `Flow`, subscriber điều chỉnh số phần tử được phép phát bằng `subscription.request(n)`. Nếu chỉ request 1 mà chưa xử lý xong, publisher có thể lưu những item tiếp theo trong buffer. Khi buffer đạt giới hạn, producer phải đối mặt với chính sách xử lý của `submit` hoặc `offer`.

~~~text
subscriber: request(1)
producer:   A, B, C, D, E, ...
               |
publisher -> onNext(A)  (đủ demand)
          -> buffer(B,C,... ) khi còn capacity
          -> capacity đầy: submit đợi hoặc offer drop/timeout
subscriber: onNext(A) xong, request(1)
publisher -> onNext(B) ...
~~~

Điểm cần phân biệt:

- **Demand** (`request(n)`): subscriber cấp quyền phát tối đa `n` item chưa được đáp ứng.
- **Buffer capacity**: số item chưa được gửi tới subscriber có thể tạm lưu trong publisher; đây không phải số item subscriber đang được phép nhận.
- **Executor parallelism**: nguồn lực chạy callbacks. Nhiều worker hơn có thể giúp nhiều subscribers tiến triển, nhưng không thay thế demand, không tăng buffer capacity và không bắt subscriber xử lý nhanh hơn.
- **Producer rate**: tốc độ tạo và gửi item. Nếu nhanh hơn lâu dài so với tốc độ xử lý, buffer sẽ đầy, cho dù bắt đầu rất lớn.

Đối với một subscriber, các tín hiệu `onNext` được gửi theo thứ tự và không chạy đồng thời trên cùng subscription; một executor nhiều thread không biến việc gọi `onNext` trên **cùng subscriber** thành xử lý song song tự do. Các subscriber độc lập có thể được dispatch song song nếu executor có khả năng.

Ví dụ: hai subscribers nhận cùng 100 item, subscriber nhanh request tiếp liên tục nhưng subscriber chậm dừng request. Buffer chậm có thể đầy và khiến `submit` từ producer bị giữ lại, mặc dù subscriber nhanh còn demand. Vì thế phải đặt chính sách cho **slowest subscriber** khi hệ thống không chấp nhận producer chờ vô hạn.

## 5. `submit()` và `offer()` có hợp đồng khác nhau

| Phương thức | Khi chưa có chỗ trong buffer của subscriber | Kết quả trả về |
|---|---|---|
| `submit(item)` | Có thể **chờ không thể ngắt** đến khi có tài nguyên | Ước lượng **maximum lag** của các subscriber; ≥1 nếu có subscriber, 0 nếu không |
| `offer(item, onDrop)` | Không chờ dung lượng; có thể drop ở subscriber quá chậm, gọi handler | Số âm: ước lượng số lần drop; số không âm: ước lượng maximum lag |
| `offer(item, timeout, unit, onDrop)` | Có thể đợi đến timeout hoặc bị interrupt; có cơ hội gọi handler và retry một lần nếu trả `true` | Cùng quy ước số âm / không âm |

`submit()` **không chờ subscriber xử lý xong từng item** nếu buffer còn chỗ. Nhưng khi thiếu dung lượng, phương thức này có thể block. Hợp đồng Java 21 mô tả việc chờ tài nguyên của `submit` là *uninterruptible*. Vì vậy nếu cần timeout trong luồng phát item, cân nhắc overload `offer` có thời hạn, giới hạn upstream hoặc kiến trúc tránh vòng chờ vô hạn.

`offer()` có thể drop item **đối với một hoặc nhiều subscriber**; không đồng nghĩa một item bị drop ở mọi nơi. Callback `onDrop` nhận subscriber bị nghẽn và item; trả `true` chỉ yêu cầu publisher **thử lại một lần** tại subscriber đó, không hứa sẽ đưa item thành công. Trả `false` chấp nhận drop. Đừng thực hiện logic phức tạp, gọi đệ quy vào publisher hay chặn lâu trong drop handler; các lời gọi khác vào publisher có thể bị giữ trong khi handler chạy.

Đừng dùng kết quả `submit()` (lag) làm số lượng đã xử lý chính xác. `estimateMaximumLag()`, `estimateMinimumDemand()` là **số ước lượng dành cho monitoring**, có thể chậm so với thực tế và không nên làm điều kiện đồng bộ/chứng minh đã giao đủ item.

## 6. Ví dụ đầy đủ: buffer 1, offer drop, executor virtual thread

Ví dụ này chủ động **chưa request** khi subscriber mới được đăng ký. Buffer chỉ có dung lượng 1: item đầu được giữ lại, item thứ hai không còn chỗ nên bị drop. Sau đó subscriber request 1 để xử lý item đầu. Executor chạy callback trên **virtual thread** (JDK 21+).

Tạo file **`SubmissionOfferDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class SubmissionOfferDemo {
    public static void main(String[] args) throws Exception {
        CountDownLatch subscribed = new CountDownLatch(1);
        CountDownLatch completed = new CountDownLatch(1);
        AtomicReference<Flow.Subscription> subscription = new AtomicReference<>();

        try (ExecutorService delivery =
                     Executors.newVirtualThreadPerTaskExecutor();
             SubmissionPublisher<Integer> publisher =
                     new SubmissionPublisher<>(delivery, 1)) {

            publisher.subscribe(new Flow.Subscriber<Integer>() {
                @Override
                public void onSubscribe(Flow.Subscription s) {
                    subscription.set(s);
                    subscribed.countDown();
                    // Chủ động chưa request, để minh họa buffer đầy.
                }

                @Override
                public void onNext(Integer item) {
                    System.out.println("received=" + item
                            + " virtual=" + Thread.currentThread().isVirtual());
                }

                @Override
                public void onError(Throwable error) {
                    System.out.println("error=" + error.getClass().getSimpleName());
                    completed.countDown();
                }

                @Override
                public void onComplete() {
                    System.out.println("complete");
                    completed.countDown();
                }
            });

            if (!subscribed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Missing onSubscribe");
            }

            int first = publisher.offer(10, (subscriber, item) -> false);
            int second = publisher.offer(20, (subscriber, item) -> false);
            System.out.println("first-accepted=" + (first >= 0));
            System.out.println("second-dropped=" + (second < 0));

            subscription.get().request(1);  // Giờ cho phép nhận item 10.
            publisher.close();

            if (!completed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Missing terminal signal");
            }
        }
    }
}
~~~

Chạy:

~~~bash
javac SubmissionOfferDemo.java
java SubmissionOfferDemo
~~~

Stdout:

~~~text
first-accepted=true
second-dropped=true
received=10 virtual=true
complete
~~~

Giải thích cơ chế thực tế:

1. `CountDownLatch subscribed` đảm bảo callback `onSubscribe` đã thực thi **trước** hai lời gọi `offer`, tránh phụ thuộc may rủi của lịch thread.
2. Subscriber chưa gọi `request` nên item 10 được xếp vào buffer dung lượng 1. Item 20 hết chỗ và `onDrop` trả `false`, vì thế giá trị `second` âm.
3. `request(1)` sau hai lời `println` mở demand để phát item 10. Do đó stdout có thứ tự nêu trên.
4. `onNext` chạy trên virtual thread của executor đã cấp và `isVirtual()` là `true`. **Điều này không biến mỗi item thành một virtual thread riêng được bảo đảm**; implementation có thể dispatch một nhóm tín hiệu trong cùng task.
5. `publisher.close()` sau request yêu cầu tín hiệu kết thúc; latch giữ chương trình đến lúc subscriber nhận `onComplete`. Item 20 đã drop nên không được phát.

Ở code thực tế, subscriber nên request theo tốc độ có thể xử lý, **không cố tình ngưng request mãi**; ở đây ta cố ý giữ demand bằng 0 để giải thích sự khác nhau giữa demand và buffer.

## 7. Chọn executor: tài nguyên, cách ly và nguy cơ bế tắc

Lựa chọn executor có tác động trực tiếp đến khả năng giải phóng buffer.

### 7.1. `ForkJoinPool.commonPool()` mặc định

Dùng khi workload nhỏ, ngắn, callback không chặn lâu và không cần kiểm soát lifecycle executor riêng. Nhưng `commonPool` là tài nguyên chia sẻ của JVM: các công việc khác có thể chiếm worker và làm delivery chậm. Khi callback gọi API blocking nặng hoặc CPU-bound lâu, cần đo ảnh hưởng đến các tác vụ khác cùng pool.

### 7.2. `Executors.newFixedThreadPool(n)`

Thích hợp để cách ly delivery và đặt một giới hạn hữu hạn về **số worker đồng thời xử lý callbacks**. Khi có vài subscriber chủ yếu xử lý CPU hoặc công việc ngắn, fixed pool thường dễ dự đoán. Khi mỗi `onNext` lại đợi I/O lâu, ít worker có thể tạo nút cổ chai và làm buffer đầy. Khả năng xử lý còn phụ thuộc queue của executor, số subscriber và độ dài callback.

### 7.3. `Executors.newVirtualThreadPerTaskExecutor()` (Java 21+)

Phù hợp nếu callback thực sự phải dùng API blocking I/O tương thích, muốn giữ cách viết tuần tự và có thể có rất nhiều delivery tasks chờ. Tuy vậy, executor này không tự hạn chế số virtual thread được tạo và không thay thế giới hạn DB connection, HTTP rate limit hay timeout. Việc tăng số virtual thread không làm subscriber thiếu demand tự nhận thêm item.

### 7.4. Tránh tự gây starvation/deadlock

Một lỗi điển hình: producer chạy **trên cùng một single-thread executor** dùng làm delivery executor. Producer gọi `submit()` liên tục, buffer đầy và phải chờ; nhưng worker duy nhất đang bị chiếm bởi producer, nên callback `onNext` không có worker để tiến triển, không thể gửi `request` tiếp. Kết quả có thể là deadlock.

~~~text
single-thread executor:
  Worker #1 đang chạy producer:
    submit(A) -> submit(B) -> ... -> buffer đầy -> chờ
  Delivery task onNext(...) đang đợi chạy trên chính Worker #1
  => Không có ai rút buffer hoặc request thêm demand
~~~

Hạn chế nguy cơ bằng cách tách producer khỏi delivery executor, đảm bảo đủ khả năng chạy độc lập cho callback, không chặn worker duy nhất bằng `submit`, dùng `offer` có timeout/drop khi phù hợp và có chính sách backpressure ở upstream. Không có một cấu hình thread count phù hợp cho tất cả; cần kiểm thử bằng số subscriber và tốc độ thực tế.

**Lưu ý:** `newSingleThreadExecutor()` không mặc nhiên sai. Nó phù hợp với quy trình chỉ cần một luồng giao tín hiệu và không đẩy nó vào vòng chờ phụ thuộc chính nó. Vấn đề là dependency cycle giữa producer, callbacks và request.

## 8. Vòng đời và lỗi trong Subscriber

- `publisher.close()`: ngừng chấp nhận phần tử mới, phát tín hiệu `onComplete` khi các item hợp lệ đã được xử lý theo protocol; việc thông báo bất đồng bộ có thể chưa xong khi `close()` trả về.
- `publisher.closeExceptionally(cause)`: chấm dứt bất thường và gửi `onError(cause)`; subscriber phải dừng và xử lý lỗi. `getClosedException()` hỗ trợ truy vấn nguyên nhân đóng bất thường.
- `subscription.cancel()`: hủy một subscription; không đóng publisher hay executor và không phải cơ chế báo thành công.
- `onNext` ném exception: subscription tương ứng bị hủy. Constructor overload có `BiConsumer<Subscriber,Throwable>` xử lý lỗi trong `onNext` **trước khi hủy**, không phải exception handler chung cho mọi callback.
- Nếu `onSubscribe`, `onError` hoặc `onComplete` tự ném exception, handler riêng cho `onNext` không nhận các lỗi đó.
- Executor có thể ném `RejectedExecutionException` (ví dụ bị shutdown quá sớm), khiến `submit`/`offer` ném exception và không phải mọi subscriber đều nhận item; hệ thống nên có chính sách đóng bất thường và thông báo/cảnh báo thích hợp.

Snippet cấu hình handler lỗi `onNext`:

~~~java
// Snippet: delivery là Executor đã được tạo và sẽ đóng riêng.
SubmissionPublisher<String> publisher = new SubmissionPublisher<>(
        delivery,
        32,
        (subscriber, error) -> {
            System.err.println("onNext failed: " + error.getMessage());
        }
);
~~~

Đây là snippet, không có `main`. Không dùng handler để giả định có thể tiếp tục subscription đã bị hủy. Lỗi nghiệp vụ nên được phản ánh qua cơ chế phù hợp: dữ liệu lỗi, retry upstream với giới hạn, hoặc `closeExceptionally` toàn stream.

Nếu cấp `ExecutorService` riêng cho publisher, **cần đóng publisher trước và sau đó đóng executor**. Việc gọi `close()` trên publisher không đồng nghĩa gọi `executor.shutdown()`. Với `commonPool` mặc định, **không tự shutdown shared common pool** chỉ vì publisher của mình hoàn tất. Khi cần đợi công việc hoàn tất, dùng `CountDownLatch`/`CompletableFuture` có timeout, không dựa vào `Thread.sleep` rồi phỏng đoán.

## 9. Đo lường, capacity và thiết kế dữ liệu

Capacity `getMaxBufferCapacity()` tính theo **mỗi subscriber**, không phải hàng đợi chung cho toàn publisher. Có N subscribers, mỗi subscriber có buffer tối đa C phần tử; số item giữ trong các buffer có thể tăng theo N × C, chưa kể bản thân object, queue/task của executor và các reference khác. Nếu item lớn hoặc subscribers chậm, tổng heap có thể đáng kể.

Giả sử có 40 subscribers, mỗi buffer có thể giữ 128 **tham chiếu** item thì có thể có đến 5.120 slot tham chiếu trong các buffer (chưa kể object thực tế và overhead). Đây là ví dụ định cỡ, **không phải đo bộ nhớ cụ thể** hay khẳng định toàn bộ item được sao chép thành N object riêng; nhiều buffer có thể giữ reference đến cùng item.

Quan sát các chỉ số:

- Số subscribers, tốc độ publish, tốc độ `onNext` hoàn thành và tỷ lệ xử lý lỗi.
- `estimateMaximumLag()`, `estimateMinimumDemand()`: chỉ số gần đúng để theo dõi tình trạng demand và lag, **không dùng để chứng minh synchronization**.
- Tỷ lệ `offer` trả giá trị âm, số subscriber bị drop và retry thất bại.
- Executor pool queue/active workers, CPU và thời gian callback (nếu dùng fixed pool).
- Với virtual thread executor: số task đang sống, thời gian chờ I/O, memory, thread-local allocation và giới hạn kết nối.
- Timeout/cancellation ở network và downstream, p95/p99 end-to-end latency, số lần producer bị chặn khi `submit`.

Từ đây lựa chọn capacity dựa trên peak burst thực tế, kích thước item, độ trễ callback và mức tiêu thụ heap chấp nhận được. Đặt capacity lớn hơn có thể hấp thụ burst nhưng **không sửa được mismatch tốc độ kéo dài** giữa producer và subscriber.

## 10. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách sửa |
|---|---|---|
| Tưởng `submit` đồng bộ gọi `onNext` ngay | Race và thứ tự output khó dự đoán | Hiểu dispatch bất đồng bộ, đợi terminal đúng cách |
| Tưởng executor chỉ dùng để chạy producer | Cấp thread sai chỗ | Executor dùng cho các tác vụ delivery/callback |
| Gọi `request(0)` vì chưa muốn nhận item | Protocol error | Đừng request khi chưa muốn; khi cần hãy request số dương |
| Gọi `request(Long.MAX_VALUE)` cho subscriber xử lý rất chậm | Có thể tạo áp lực buffer/tài nguyên | Request theo khả năng xử lý, theo dõi lag |
| Dùng `submit` khi không thể chấp nhận blocking | Producer có thể chờ không giới hạn | `offer` có timeout/drop và backpressure trước publisher |
| Coi `offer` âm là lỗi cho mọi subscriber | Đọc sai drop semantics | Drop có thể chỉ xảy ra ở một số subscriptions |
| Tin executor nhiều thread giúp một subscriber `onNext` chạy song song | Hiểu sai contract | Song song ở các subscriptions, không vi phạm thứ tự tín hiệu một subscription |
| Producer và delivery dùng một single-thread executor gây vòng chờ | Starvation/deadlock | Tách executors hoặc thiết kế tránh phụ thuộc vòng |
| Shutdown executor trước khi các callbacks/terminal signal hoàn tất | `RejectedExecutionException`, thiếu signal | Đóng publisher, đợi terminal, sau đó đóng executor |
| Xem `close()` là `onComplete()` đã chạy xong | Program thoát sớm, test flaky | Dùng latch/future chờ callback có timeout |
| Xem lag estimate là số tuyệt đối cho synchronization | Quyết định sai do số liệu có thể stale | Chỉ dùng cho monitoring |

## 11. Câu hỏi tự kiểm tra

**Câu 1:** `new SubmissionPublisher<>()` mặc định có tạo một pool mới riêng không? **Không theo hợp đồng API.** Nó sử dụng common pool nếu parallelism đủ 2, nếu không có cơ chế tạo thread thay thế.

**Câu 2:** Producer gọi `submit(A)` rồi `submit(B)`. Có chắc `onNext(A)` đã chạy xong trước khi `submit(B)` trả về không? **Không.** Publication và delivery là bất đồng bộ; item có thể nằm trong buffer.

**Câu 3:** Hai subscribers, một nhanh và một chậm. Vì sao producer có thể bị `submit` giữ lại? **Vì buffer của subscriber chậm có thể đầy**, dù subscriber nhanh còn demand.

**Câu 4:** `offer(item, (s,i)->false)` trả về `-1` thì có ý nghĩa gì? **Có một drop được báo trong lời gọi này**, không có nghĩa publisher đã đóng hoặc mọi subscriber đều nhận lỗi.

**Câu 5:** Dùng `newVirtualThreadPerTaskExecutor()` có loại bỏ nhu cầu `request(n)` không? **Không.** Executor chỉ quyết định nơi callback chạy, không sửa protocol demand.

**Câu 6:** Dừng `SubmissionPublisher` có tự đóng `ExecutorService` mà caller đã truyền vào không? **Không.** Caller phải quản lý vòng đời executor riêng.

### Bài tập

1. Đổi `SubmissionExecutorDemo` từ fixed pool 2 thành fixed pool 1, quan sát tên thread/cờ `isVirtual()`. Giải thích vì sao thứ tự item trong một subscriber vẫn giữ.
2. Trong `SubmissionOfferDemo`, gọi `request(2)` trước khi offer. Lý giải vì sao hai item có thể được chấp nhận (trong điều kiện subscriber chưa hủy và executor hoạt động); không dựa vào sleep để đồng bộ.
3. Tạo hai subscribers, một request từng item và một cố tình giữ demand. Thử `submit` với buffer nhỏ, sau đó thử `offer` có timeout để quan sát tình huống producer có thể phải chờ và các drop.
4. Thêm `onNext` cố ý ném `IllegalStateException` và cấu hình constructor handler. Quan sát cancellation và cách đóng publisher, nhưng không dùng sự cố này làm tín hiệu thành công trong code sản xuất.

## 12. Ghi nhớ

- `SubmissionPublisher<T>` là publisher bất đồng bộ có sẵn của `Flow`; **executor dùng để giao tín hiệu đến subscriber**, còn producer tự quyết định khi nào tạo/gửi item.
- Mặc định dùng common pool khi đủ parallelism; có thể cấp `Executor` riêng và buffer capacity theo từng subscriber bằng constructor.
- **Backpressure** dựa trên `Subscription.request(n)`; buffer chỉ hấp thụ chênh lệch tốc độ tạm thời.
- `submit()` có thể block khi đầy; `offer()` có thể drop hoặc timeout với handler và chính sách retry một lần.
- Số thread/virtual thread của executor không thay thế hạn mức downstream, backpressure, timeout hay xử lý subscriber chậm.
- `close()` và terminal callback là các sự kiện khác nhau; quản lý executor và chờ completion rõ ràng để tránh dừng sớm hay reject task.

### Tham khảo chính thức

- Java SE 21 `SubmissionPublisher` API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html
- Java SE 21 `Flow` API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.html
- Java SE 21 `Flow.Subscription` API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscription.html
- Java SE 21 `Executor` API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executor.html
- Java SE 21 `Executors` API: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Executors.html
