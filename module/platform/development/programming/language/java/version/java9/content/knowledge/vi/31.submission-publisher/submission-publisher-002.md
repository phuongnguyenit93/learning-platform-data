# Chọn Executor và dung lượng bộ đệm cho `SubmissionPublisher`

`SubmissionPublisher<T>` là một implementation của `Flow.Publisher<T>` được bổ sung trong Java 9. Publisher gửi phần tử bất đồng bộ đến các `Flow.Subscriber` theo cơ chế demand của Flow API. Khi cấu hình publisher, hai quyết định quan trọng là executor thực thi các callback của subscriber và dung lượng buffer dành cho từng subscriber.

Executor quyết định callback được chạy trên những thread nào và mức độ cô lập giữa các subscriber. Buffer quyết định publisher có thể giữ bao nhiêu phần tử đang chờ một subscriber tiêu thụ. Hai cấu hình này có liên quan nhưng là hai nguồn giới hạn khác nhau: tăng buffer không làm executor xử lý nhanh hơn, còn tăng số worker không giải quyết được subscriber liên tục yêu cầu dữ liệu chậm hơn tốc độ phát.

## 1. `SubmissionPublisher` tổ chức việc phân phối như thế nào?

Publisher nhận phần tử qua `submit()` hoặc `offer()` rồi phân phối bất đồng bộ đến các subscriber hiện tại. Mỗi subscriber có buffer riêng. Subscriber chỉ nhận dữ liệu khi đã yêu cầu demand thông qua `Flow.Subscription.request(n)`.

Luồng dữ liệu có thể hình dung như sau:

```text
Producer
   | submit(item) / offer(item)
   v
SubmissionPublisher
   |                         |
   v                         v
Buffer của subscriber A     Buffer của subscriber B
   |                         |
   v                         v
Executor chạy callback      Executor chạy callback
   |                         |
   v                         v
onNext(item)                 onNext(item)
```

Buffer là vùng đệm cho các phần tử đã được publisher nhận nhưng subscriber chưa tiêu thụ. Demand không phải dung lượng buffer: demand cho biết subscriber sẵn sàng nhận bao nhiêu phần tử; buffer giới hạn số phần tử có thể chờ được giao cho subscriber đó.

Subscriber có thể yêu cầu từng phần tử, một số lượng hữu hạn hoặc gần như không giới hạn bằng `request(Long.MAX_VALUE)`. Nếu subscriber không yêu cầu thêm dữ liệu, phần tử mới sẽ tiếp tục nằm trong buffer cho đến khi buffer đầy.

## 2. Chọn Executor

Constructor cho phép chỉ định executor:

```java
SubmissionPublisher<T> publisher =
        new SubmissionPublisher<>(executor, maxBufferCapacity);
```

Executor được dùng để thực thi các tác vụ phân phối tín hiệu đến subscriber, chẳng hạn `onNext`, `onError` và `onComplete`. Vì callback có thể chạy bất đồng bộ, producer không nên giả định rằng `submit()` sẽ gọi `onNext()` ngay trên thread đang submit.

Constructor mặc định dùng `ForkJoinPool.commonPool()` và dung lượng buffer mặc định lấy từ `Flow.defaultBufferSize()`. Đây là lựa chọn thuận tiện cho callback ngắn, không block và tải vừa phải. Khi callback thực hiện I/O blocking, xử lý lâu hoặc cần cách ly với công việc khác trong JVM, hãy cân nhắc truyền executor riêng.

### Executor cho callback ngắn và thiên về CPU

Với callback thực hiện phép biến đổi nhỏ, tính toán nhanh hoặc cập nhật trạng thái trong bộ nhớ, một pool có số worker hữu hạn thường dễ kiểm soát. Có thể bắt đầu bằng số worker gần số CPU khả dụng rồi đo throughput và độ trễ dưới tải thực tế.

Không tăng số thread chỉ vì thấy buffer tăng. Nếu công việc chủ yếu dùng CPU, quá nhiều worker có thể làm tăng context switching và tranh chấp tài nguyên.

### Executor cho callback có blocking I/O

Nếu `onNext()` đọc file, gọi dịch vụ mạng hoặc chờ database, thread xử lý có thể bị giữ trong lúc chờ I/O. Dùng executor riêng giúp cô lập các callback đó khỏi common pool hoặc pool dành cho tính toán.

Không nên để callback block chờ một tác vụ khác cần chính executor đó. Ví dụ, nếu tất cả worker đều đang chạy `onNext()` và gọi `Future.get()` để chờ tác vụ được submit vào cùng pool, các tác vụ được chờ có thể không còn worker để chạy. Đây là một dạng thread starvation.

Giữ callback ngắn khi có thể. Nếu cần xử lý tiếp ở một executor khác, hãy thiết kế việc chuyển giao có giới hạn và vẫn kiểm soát demand; đừng yêu cầu thêm dữ liệu ngay sau khi chỉ mới đưa công việc vào một queue khác nếu mục tiêu là backpressure phải phản ánh thời gian xử lý thực tế.

### Executor phải có năng lực tiếp nhận tác vụ

Executor riêng nên có chính sách rõ ràng về số worker, queue và rejection. Queue không giới hạn có thể tăng mãi khi tốc độ submit vượt khả năng phân phối. Queue quá nhỏ có thể từ chối tác vụ khi hệ thống có burst.

`SubmissionPublisher` có buffer riêng cho từng subscriber, còn queue của `ThreadPoolExecutor` là hàng đợi tác vụ của executor. Không được cộng hai con số này thành một dung lượng chung hoặc coi chúng thay thế nhau. Nếu executor bị bão hòa và từ chối tác vụ phân phối, việc giao tín hiệu đến subscriber có thể không hoàn tất như mong đợi; cần kiểm thử rejection behavior của cấu hình thực tế.

Tránh chọn `CallerRunsPolicy` một cách máy móc. Chính sách này có thể làm thread gọi `submit()` chạy tác vụ bị từ chối, khiến producer bất ngờ thực hiện callback và bị chặn bởi công việc của subscriber. Chọn rejection policy dựa trên latency, luồng gọi và cách ứng dụng xử lý quá tải.

## 3. Chọn dung lượng buffer

Tham số `maxBufferCapacity` trong constructor là dung lượng tối đa của buffer cho **mỗi subscriber**. Nó không phải tổng dung lượng dùng chung cho toàn publisher.

```java
SubmissionPublisher<Integer> publisher =
        new SubmissionPublisher<>(executor, 3);

System.out.println(publisher.getMaxBufferCapacity());
```

Dung lượng yêu cầu được làm tròn lên lũy thừa của hai gần nhất. Vì vậy, yêu cầu `3` có dung lượng thực tế là `4`; dùng `getMaxBufferCapacity()` để kiểm tra giá trị publisher đang sử dụng. Dung lượng phải là số dương.

Buffer lớn có thể hấp thụ burst tốt hơn và giảm số lần producer phải chờ hoặc phải bỏ phần tử. Đổi lại, mỗi subscriber có thể giữ nhiều tham chiếu đến phần tử chưa được tiêu thụ hơn, làm tăng bộ nhớ và có thể giữ object sống lâu hơn. Buffer lớn cũng có thể che giấu subscriber chậm trong một khoảng thời gian, khiến độ trễ tích lũy trước khi vấn đề lộ rõ.

Buffer nhỏ giới hạn bộ nhớ và làm áp lực từ subscriber chậm xuất hiện sớm hơn. Producer có thể phải chờ thường xuyên hơn khi dùng `submit()`, hoặc phải xử lý việc drop khi dùng `offer()`.

### Ước lượng bộ nhớ

Với `S` subscriber, capacity thực tế `C` và kích thước tham chiếu/phần tử trung bình `M`, lượng dữ liệu được giữ trong các buffer có thể ước lượng sơ bộ theo `S × C × M`, cộng thêm overhead của buffer, subscriber và executor. Đây chỉ là ước lượng: publisher giữ tham chiếu đến object, không nhất thiết tạo bản sao độc lập của từng phần tử cho từng subscriber.

Ví dụ, capacity 256 với 100 subscriber có thể giữ đến khoảng 25.600 vị trí phần tử đang chờ trên toàn bộ các buffer, chưa tính overhead và queue của executor. Nếu phần tử chứa object lớn hoặc giữ theo một đồ thị object lớn, tác động bộ nhớ có thể cao hơn nhiều so với kích thước tham chiếu.

## 4. Demand, subscriber chậm và backpressure

Subscriber điều khiển tốc độ nhận dữ liệu bằng subscription:

```java
subscription.request(1);
```

Trong ví dụ trên, subscriber chỉ yêu cầu thêm một phần tử sau khi xử lý phần tử hiện tại. Cách này giúp demand phản ánh sát hơn khả năng xử lý thực tế. Nếu gọi `request(Long.MAX_VALUE)`, subscriber báo rằng nó sẵn sàng nhận mọi phần tử publisher có thể giao; điều đó không có nghĩa callback thực sự xử lý vô hạn nhanh hoặc buffer không còn cần thiết.

Mỗi subscriber có buffer riêng nên tốc độ tiêu thụ của từng subscriber có thể khác nhau. Một subscriber chậm sẽ làm buffer của chính nó đầy trước. Với nhiều subscriber, cần quyết định publisher phải chờ subscriber chậm hay chấp nhận bỏ dữ liệu cho subscriber đó.

Backpressure chỉ có tác dụng nếu producer tôn trọng tín hiệu quá tải. Nếu producer tiếp tục tạo và giữ dữ liệu ở một queue khác không giới hạn, buffer của `SubmissionPublisher` không thể bảo vệ toàn bộ ứng dụng khỏi tăng bộ nhớ.

## 5. `submit()` hay `offer()`?

`submit(item)` gửi phần tử đến các subscriber hiện tại. Khi buffer của subscriber không còn chỗ, lời gọi có thể block cho đến khi có chỗ trống. Việc chờ này là uninterruptible trong lúc tài nguyên chưa sẵn sàng; nếu thread bị interrupt trong khi chờ, trạng thái interrupt được khôi phục trước khi phương thức trả về. Vì vậy, không nên gọi `submit()` trên event loop hoặc thread nhạy cảm với latency nếu subscriber có thể chậm.

Phương thức trả về một ước lượng về độ trễ lớn nhất (số phần tử đã gửi nhưng subscriber chưa tiêu thụ) trong các subscriber hiện tại. Đây là số liệu ước lượng để quan sát, không phải cam kết đồng bộ về trạng thái của tất cả subscriber.

`offer(item, onDrop)` thử gửi mà không chờ vô hạn. Nếu buffer của một subscriber đầy, phần tử có thể bị bỏ cho subscriber đó và callback `onDrop` được gọi để ứng dụng xử lý. Có overload nhận timeout để chờ buffer trong một khoảng thời gian giới hạn trước khi quyết định bỏ phần tử.

Giá trị trả về của `offer()` là ước lượng lag; giá trị âm cho biết phần tử đã bị bỏ đối với ít nhất một subscriber. Hãy đọc kết quả và thiết kế chính sách drop rõ ràng, ví dụ ghi metric, đếm số lần drop, bỏ dữ liệu cũ hoặc yêu cầu producer giảm tốc độ.

| API | Hành vi khi subscriber hết chỗ | Khi phù hợp |
| --- | --- | --- |
| `submit(item)` | Có thể block đến khi có chỗ | Không được phép mất dữ liệu và producer có thể chờ |
| `offer(item, onDrop)` | Thử gửi, xử lý drop qua callback | Cần tránh block vô hạn và có chính sách drop |
| `offer(item, timeout, unit, onDrop)` | Chờ có giới hạn rồi xử lý drop | Chấp nhận một thời gian chờ tối đa rõ ràng |

Không có lựa chọn nào đúng cho mọi ứng dụng. Dữ liệu tài chính hoặc sự kiện nghiệp vụ quan trọng có thể cần chờ hoặc lưu bền vững thay vì drop. Telemetry hoặc cập nhật trạng thái mới nhất có thể chấp nhận drop có kiểm soát nếu dữ liệu cũ không còn giá trị.

## 6. Cấu hình capacity theo workload

Không nên chọn capacity chỉ dựa trên một con số mặc định. Hãy xem xét:

1. **Burst size:** producer có thể gửi dồn bao nhiêu phần tử trong khoảng thời gian subscriber chưa kịp xử lý?
2. **Tốc độ tiêu thụ:** subscriber xử lý trung bình bao nhiêu phần tử mỗi giây?
3. **Số subscriber:** mỗi subscriber có buffer riêng nên tổng bộ nhớ tăng theo số subscriber.
4. **Kích thước phần tử:** phần tử lớn hoặc giữ nhiều object khác có thể chiếm bộ nhớ đáng kể.
5. **Độ trễ cho phép:** buffer lớn có thể giữ sự kiện lâu hơn trước khi subscriber xử lý.
6. **Chính sách quá tải:** producer được phép block, chờ có timeout hay phải bỏ phần tử?
7. **Năng lực executor:** callback có đủ worker và thời gian CPU/I/O để tiêu thụ dữ liệu không?

Nếu tốc độ producer lâu dài cao hơn tốc độ consumer, mọi buffer hữu hạn cuối cùng cũng đầy. Tăng capacity chỉ kéo dài thời gian trước khi áp lực xuất hiện; cần tăng năng lực xử lý, giảm tốc độ phát, phân phối tải hoặc thay đổi chính sách quá tải.

## 7. Ví dụ hoàn chỉnh: cấu hình Executor và kiểm tra capacity thực tế

Ví dụ sau dùng `ThreadPoolExecutor` có hai worker và queue giới hạn. Publisher được yêu cầu capacity 3; chương trình đọc capacity thực tế qua `getMaxBufferCapacity()`. Subscriber yêu cầu từng phần tử, ghi nhận dữ liệu nhận được rồi yêu cầu phần tiếp theo.

Tạo tệp `SubmissionPublisherCapacityDemo.java`:

```java
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public class SubmissionPublisherCapacityDemo {
    public static void main(String[] args) throws Exception {
        ThreadPoolExecutor executor = new ThreadPoolExecutor(
                2, 2, 0L, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(32),
                new ThreadPoolExecutor.AbortPolicy());
        CountDownLatch received = new CountDownLatch(3);
        CountDownLatch completed = new CountDownLatch(1);
        List<Integer> receivedItems = new CopyOnWriteArrayList<>();
        AtomicReference<Throwable> failure = new AtomicReference<>();
        int actualCapacity;
        int subscriberCount;

        try {
            try (SubmissionPublisher<Integer> publisher =
                         new SubmissionPublisher<>(executor, 3)) {
                actualCapacity = publisher.getMaxBufferCapacity();
                publisher.subscribe(new Flow.Subscriber<Integer>() {
                    private Flow.Subscription subscription;

                    @Override
                    public void onSubscribe(Flow.Subscription subscription) {
                        this.subscription = subscription;
                        subscription.request(1);
                    }

                    @Override
                    public void onNext(Integer item) {
                        receivedItems.add(item);
                        received.countDown();
                        subscription.request(1);
                    }

                    @Override
                    public void onError(Throwable throwable) {
                        failure.set(throwable);
                        completed.countDown();
                    }

                    @Override
                    public void onComplete() {
                        completed.countDown();
                    }
                });

                publisher.submit(10);
                publisher.submit(20);
                publisher.submit(30);
                subscriberCount = publisher.getNumberOfSubscribers();
            }

            if (!received.await(2, TimeUnit.SECONDS)
                    || !completed.await(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Subscriber did not complete in time");
            }
            if (failure.get() != null) {
                throw new IllegalStateException("Subscriber failed", failure.get());
            }

            System.out.println("Actual buffer capacity: " + actualCapacity);
            System.out.println("Subscribers before close: " + subscriberCount);
            System.out.println("Received items: " + receivedItems);
            System.out.println("Completed: true");
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
```

Biên dịch và chạy bằng JDK 9 trở lên:

```bash
javac --release 9 -Xlint:all SubmissionPublisherCapacityDemo.java
java SubmissionPublisherCapacityDemo
```

Kết quả stdout:

```text
Actual buffer capacity: 4
Subscribers before close: 1
Received items: [10, 20, 30]
Completed: true
```

Constructor nhận capacity `3` nhưng publisher báo capacity thực tế `4` vì giá trị được làm tròn lên lũy thừa của hai. Subscriber yêu cầu từng phần tử và nhận đủ ba phần tử. Khi publisher được đóng, subscriber nhận `onComplete()` sau các phần tử đã được gửi. Executor chỉ được shutdown sau khi subscriber hoàn tất.

Queue 32 trong `ThreadPoolExecutor` là queue của executor; capacity 4 là buffer riêng của subscriber. Chúng phục vụ hai mục đích khác nhau và cần được điều chỉnh độc lập.

## 8. Quan sát và điều chỉnh khi chạy thực tế

`SubmissionPublisher` cung cấp một số phương thức hỗ trợ quan sát:

- `getMaxBufferCapacity()` trả về capacity tối đa thực tế của mỗi subscriber.
- `getNumberOfSubscribers()` trả về số subscriber hiện tại.
- `hasSubscribers()` cho biết hiện có subscriber hay không.
- `estimateMaximumLag()` ước lượng lag lớn nhất giữa các subscriber.
- `estimateMinimumDemand()` ước lượng demand nhỏ nhất trong các subscriber.

Các giá trị lag và demand là ước lượng tại thời điểm gọi; không dùng chúng như phép kiểm tra khóa hoặc điều kiện đảm bảo rằng trạng thái không đổi ngay sau đó. Chúng hữu ích cho metric, log và quyết định điều chỉnh tải.

Nên theo dõi thêm số lần `offer()` drop, thời gian `submit()` bị block, queue size của executor, active worker, rejection count, thời gian callback và độ trễ từ lúc phát đến lúc xử lý. Kết hợp các số liệu này để xác định bottleneck nằm ở subscriber, buffer hay executor.

## 9. Đóng publisher và quản lý vòng đời Executor

`SubmissionPublisher` triển khai `AutoCloseable`. Dùng try-with-resources để đóng publisher và báo hoàn tất cho subscriber. `close()` báo kết thúc bình thường sau các phần tử đã submit; `closeExceptionally(error)` kết thúc luồng bằng lỗi và subscriber nhận `onError()` theo hợp đồng Flow.

Executor truyền vào constructor do ứng dụng cung cấp và ứng dụng vẫn chịu trách nhiệm quản lý vòng đời của executor đó. Đóng publisher không đồng nghĩa executor được shutdown. Hãy đợi subscriber xử lý xong và nhận `onComplete()` khi cần, sau đó mới shutdown executor do mình sở hữu.

Không shutdown common pool hoặc executor dùng chung của thành phần khác. Nếu nhiều publisher cùng sử dụng một executor, cần có một thành phần cấp cao hơn quản lý việc shutdown để publisher còn lại không mất khả năng phân phối.

## 10. Những lỗi cấu hình thường gặp

- **Nhầm capacity là tổng dung lượng:** capacity áp dụng cho từng subscriber; tổng lượng buffer tăng theo số subscriber.
- **Chỉ tăng buffer khi consumer chậm:** buffer lớn không tăng throughput và có thể làm tăng bộ nhớ/độ trễ.
- **Dùng common pool cho callback blocking:** callback có thể chiếm worker dùng chung và làm chậm các tác vụ khác.
- **Dùng executor có queue không giới hạn:** backlog có thể tăng đến khi cạn bộ nhớ.
- **Bỏ qua demand:** subscriber không gọi `request()` sẽ không tiêu thụ dữ liệu, khiến buffer đầy.
- **Dùng `submit()` trên thread nhạy cảm với latency:** producer có thể bị block bởi subscriber chậm.
- **Dùng `offer()` nhưng không xử lý drop:** dữ liệu có thể bị bỏ cho một hoặc nhiều subscriber mà ứng dụng không nhận biết.
- **Shutdown executor quá sớm:** publisher có thể chưa phân phối xong tín hiệu hoặc subscriber chưa nhận `onComplete()`.
- **Cho rằng tăng worker luôn giải quyết quá tải:** nếu bottleneck là database, mạng hoặc subscriber xử lý chậm, thêm worker có thể làm tài nguyên đích quá tải hơn.

## 11. Quy trình chọn cấu hình

1. Đo thời gian và loại công việc trong subscriber: CPU-bound, blocking I/O hay callback rất ngắn.
2. Chọn executor phù hợp và xác định rõ số worker, queue, thread factory và rejection policy.
3. Ước lượng burst, số subscriber, kích thước phần tử và thời gian consumer có thể chưa kịp nhận dữ liệu.
4. Chọn `maxBufferCapacity` theo giới hạn bộ nhớ và độ trễ; kiểm tra giá trị thực tế bằng `getMaxBufferCapacity()`.
5. Quyết định dùng `submit()` để tạo backpressure bằng cách chờ hay `offer()` để áp dụng chính sách drop có kiểm soát.
6. Kiểm tra subscriber có request đúng theo tiến độ xử lý và callback không block chờ công việc cần cùng executor.
7. Theo dõi lag, demand, thời gian submit, queue executor và số lần drop dưới tải thực tế.
8. Kiểm thử subscriber chậm, không request, hủy subscription, executor quá tải và shutdown publisher.

Chọn Executor và dung lượng buffer là hai phần của cùng một chiến lược điều tiết tải cho `SubmissionPublisher`. Executor phải có khả năng chạy callback đúng loại workload; buffer phải đủ hấp thụ burst nhưng vẫn nằm trong giới hạn bộ nhớ và độ trễ. Khi kết hợp demand, `submit()`/`offer()` và metric phù hợp, ứng dụng có thể kiểm soát rõ cách xử lý subscriber chậm và tình trạng quá tải.