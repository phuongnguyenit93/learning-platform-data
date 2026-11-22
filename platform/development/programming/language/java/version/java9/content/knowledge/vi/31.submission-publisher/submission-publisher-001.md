# Triển khai Publisher có bộ đệm cho từng Subscriber

`SubmissionPublisher<T>` là implementation của `Flow.Publisher<T>` được cung cấp trong Java 9. Nó phát dữ liệu bất đồng bộ tới các Subscriber thông qua một `Executor` và duy trì **một bộ đệm độc lập cho từng Subscriber**. Nhờ đó, mỗi Subscriber có thể tiêu thụ dữ liệu theo tốc độ riêng trong giới hạn buffer của nó.

Thiết kế này cho phép producer và consumer tạm thời hoạt động với tốc độ khác nhau. Tuy nhiên, nếu một Subscriber chậm đến mức buffer riêng bị đầy, chính sách phát dữ liệu của Publisher sẽ quyết định producer phải chờ hay bỏ dữ liệu cho Subscriber đó. Hai lựa chọn chính là `submit()` và `offer()`.

## Mục tiêu

- Khởi tạo `SubmissionPublisher` với Executor và dung lượng buffer tối đa cho mỗi Subscriber.
- Hiểu buffer riêng được tạo và mở rộng như thế nào.
- Phân biệt buffer capacity, demand và lag.
- Chọn `submit()` hoặc `offer()` theo yêu cầu không mất dữ liệu hay giới hạn thời gian phát.
- Xử lý drop handler, retry và kết quả trả về của `offer()`.
- Theo dõi Subscriber, demand và lag bằng các API giám sát.
- Quản lý lỗi, đóng Publisher và vòng đời Executor.
- Kiểm chứng hành vi khi một Subscriber chậm còn Subscriber khác vẫn xử lý nhanh.

## 1. SubmissionPublisher trong Flow API

`SubmissionPublisher<T>` triển khai `Flow.Publisher<T>` và `AutoCloseable`. Publisher nhận các phần tử không null, sau đó gửi bất đồng bộ tới các Subscriber hiện tại theo thứ tự gửi, trừ trường hợp phần tử bị drop hoặc có lỗi.

~~~text
Producer
   | submit(item) / offer(item)
   v
SubmissionPublisher<T>
   |
   +---- Buffer riêng của Subscriber A ----> Executor ----> onNext(item)
   |
   +---- Buffer riêng của Subscriber B ----> Executor ----> onNext(item)
   |
   +---- Buffer riêng của Subscriber C ----> Executor ----> onNext(item)
~~~

Điểm khác biệt quan trọng là Publisher không dùng một hàng đợi chung duy nhất cho tất cả Subscriber. Mỗi Subscriber có buffer riêng để giữ các phần tử đang chờ được chuyển tới nó.

Ví dụ, Subscriber A có thể xử lý nhanh và buffer của nó thường rỗng, trong khi Subscriber B xử lý chậm và buffer của B đang gần đầy. Trạng thái của hai buffer được quản lý độc lập.

## 2. Khởi tạo Publisher và cấu hình dung lượng

Có thể tạo Publisher bằng constructor mặc định:

~~~java
SubmissionPublisher<String> publisher = new SubmissionPublisher<>();
~~~

Constructor mặc định dùng `ForkJoinPool.commonPool()` cho việc gửi bất đồng bộ và lấy `Flow.defaultBufferSize()` làm dung lượng tối đa cho mỗi Subscriber.

Khi cần kiểm soát tài nguyên và buffer, truyền Executor cùng dung lượng mong muốn:

~~~java
ExecutorService executor = Executors.newFixedThreadPool(4);
SubmissionPublisher<String> publisher = new SubmissionPublisher<>(
    executor, 256
);
~~~

Constructor này đặt dung lượng tối đa cho từng buffer Subscriber. Có overload thứ ba nhận một `BiConsumer<Subscriber, Throwable>` để xử lý exception phát sinh khi Subscriber ném lỗi trong `onNext()`.

~~~java
SubmissionPublisher<String> publisher = new SubmissionPublisher<>(
    executor,
    256,
    (subscriber, error) -> logSubscriberFailure(subscriber, error)
);
~~~

Giá trị dung lượng phải lớn hơn `0`. `getMaxBufferCapacity()` trả về dung lượng thực tế mà implementation áp dụng. Dung lượng thực tế có thể được làm tròn lên lũy thừa của hai hoặc bị giới hạn bởi mức tối đa mà implementation hỗ trợ.

### 2.1. Buffer được tạo khi cần

Buffer cho một Subscriber được tạo khi cần dùng lần đầu và có thể mở rộng dần cho đến dung lượng tối đa đã cấu hình. Điều đó có nghĩa là cấu hình maximum capacity không nhất thiết làm Publisher cấp phát ngay toàn bộ dung lượng cho mọi Subscriber khi vừa khởi tạo.

Khi có nhiều Subscriber, tổng lượng bộ nhớ có thể tăng theo số Subscriber và lượng dữ liệu đang chờ trong từng buffer. Nếu phần tử có kích thước lớn, cần tính đến dung lượng byte thực tế chứ không chỉ số lượng phần tử.

### 2.2. Đọc dung lượng thực tế

~~~java
int actualCapacity = publisher.getMaxBufferCapacity();
System.out.println("per-subscriber capacity: " + actualCapacity);
~~~

Không giả định constructor nhận `100` thì `getMaxBufferCapacity()` nhất thiết trả đúng `100`. Hãy đọc giá trị thực tế nếu thuật toán cần biết giới hạn buffer được áp dụng.

## 3. Buffer, demand và lag là ba khái niệm khác nhau

Ba khái niệm này có liên quan nhưng không thay thế cho nhau:

| Khái niệm | Ý nghĩa | Được điều khiển bởi |
| --- | --- | --- |
| Buffer capacity | Số phần tử tối đa có thể chờ trong buffer của một Subscriber | Constructor `SubmissionPublisher` |
| Demand | Số phần tử Subscriber đã yêu cầu nhưng chưa nhận | `Subscription.request(n)` |
| Lag | Số phần tử đã được gửi nhưng chưa được Subscriber tiêu thụ, theo ước lượng | Tốc độ producer và consumer |

`request(n)` không trực tiếp làm buffer mở rộng. Subscriber có thể yêu cầu nhiều phần tử, nhưng nếu không tiêu thụ chúng đủ nhanh, buffer vẫn có thể bão hòa ở giới hạn đã cấu hình.

Buffer giúp hấp thụ các đợt tăng dữ liệu ngắn hạn. Nó không giải quyết được tình trạng producer liên tục nhanh hơn consumer trong thời gian dài. Khi tốc độ đầu vào luôn lớn hơn tốc độ xử lý, buffer cuối cùng vẫn đầy.

## 4. submit(): giữ dữ liệu bằng cách chờ buffer

`submit(item)` phát phần tử tới tất cả Subscriber hiện tại bằng cách gọi `onNext()` bất đồng bộ. Nếu tài nguyên của bất kỳ Subscription nào chưa sẵn sàng, phương thức chặn không ngắt được cho đến khi có chỗ.

~~~java
int estimatedLag = publisher.submit("event-001");
System.out.println("estimated maximum lag: " + estimatedLag);
~~~

`submit()` là lựa chọn đơn giản khi producer không được phép bỏ phần tử do buffer đầy. Đổi lại, producer có thể phải chờ vì một Subscriber chậm.

Ví dụ: Publisher có ba Subscriber. A và B xử lý nhanh, C bị chậm và buffer của C đã đầy. Lần gọi `submit()` tiếp theo có thể phải chờ tài nguyên của C dù buffer của A và B vẫn còn chỗ.

### 4.1. submit() có thể chặn luồng gọi

Không gọi `submit()` trên event loop, UI thread hoặc luồng cần phản hồi nhanh nếu Subscriber có thể bị chậm. Producer có thể bị giữ lại trong thời gian không xác định khi buffer của một Subscriber chưa có chỗ.

Nếu producer cần tiếp tục hoạt động, cân nhắc `offer()` với chính sách drop/retry rõ ràng, hoặc đưa thao tác `submit()` sang một luồng producer riêng có khả năng chờ.

### 4.2. Giá trị trả về của submit()

`submit()` trả về ước lượng lag lớn nhất giữa các Subscriber hiện tại: số phần tử đã gửi nhưng chưa được tiêu thụ. Nếu không có Subscriber, kết quả là `0`.

Đây là số ước lượng phục vụ quan sát. Không dùng nó như số phần tử chính xác trong queue, điều kiện khóa hoặc tín hiệu đồng bộ hóa.

## 5. offer(): phát có thể bỏ phần tử khi buffer đầy

`offer(item, onDrop)` cố gắng gửi phần tử tới từng Subscriber hiện tại. Nếu buffer của một Subscriber không còn tài nguyên, phần tử có thể bị drop cho Subscriber đó. Handler được gọi để ứng dụng ghi nhận hoặc quyết định thử lại.

~~~java
int status = publisher.offer("event-002", (subscriber, item) -> {
    recordDrop(subscriber, item);
    return false;
});

if (status < 0) {
    System.out.println("number of drops: " + -status);
} else {
    System.out.println("estimated maximum lag: " + status);
}
~~~

### 5.1. Ý nghĩa của kết quả offer()

`offer()` trả về một số nguyên trạng thái:

- Nếu giá trị âm, trị tuyệt đối là số lần gửi thất bại do drop.
- Nếu giá trị không âm, đó là ước lượng lag lớn nhất giữa các Subscriber hiện tại.
- Nếu có Subscriber và không có drop, ước lượng lag tối thiểu có tính đến phần tử vừa gửi.
- Nếu không có Subscriber, ước lượng có thể là `0`.

Ví dụ, kết quả `-2` biểu thị hai lần gửi tới Subscriber bị drop. Không được hiểu `-2` là mã lỗi chung hoặc mã thoát của Publisher.

### 5.2. Drop handler và retry một lần

Drop handler có kiểu `BiPredicate<Flow.Subscriber<? super T>, ? super T>`. Nó nhận Subscriber bị thiếu chỗ và phần tử đang gửi.

- Trả `false`: không thử lại; phần tử bị drop cho Subscriber đó.
- Trả `true`: Publisher thử gửi lại một lần cho Subscriber đó.

Không có vòng retry vô hạn. Nếu retry một lần vẫn không thành công, phần tử vẫn có thể bị drop.

Handler được gọi trong lúc các thao tác khác trên cùng Publisher từ thread khác có thể bị chặn. Vì vậy, handler nên ngắn, tránh I/O blocking và không thực hiện logic phức tạp. Thông thường chỉ ghi metric/log, đánh dấu drop hoặc phát tín hiệu lỗi theo chính sách ứng dụng.

### 5.3. offer() có timeout

Overload có timeout:

~~~java
int status = publisher.offer(
    item,
    100,
    TimeUnit.MILLISECONDS,
    (subscriber, droppedItem) -> {
        recordDrop(subscriber, droppedItem);
        return false;
    }
);
~~~

Overload này có thể chờ khi tài nguyên của một Subscription chưa sẵn sàng, nhưng chỉ tối đa thời hạn được chỉ định hoặc cho tới khi thread gọi bị interrupt. Sau đó drop handler được gọi; nếu handler trả `true`, Publisher thử lại một lần.

Vì vậy, `offer()` có timeout vẫn có thể block trong khoảng thời gian giới hạn. Nếu cần API không chờ tài nguyên buffer, dùng overload không timeout.

### 5.4. Một phần tử có thể được nhận bởi Subscriber này nhưng bị drop ở Subscriber khác

Drop xảy ra theo từng Subscriber. Nếu A còn chỗ nhưng B đã đầy, Publisher có thể gửi phần tử cho A và drop phần tử đó cho B. Đây là hành vi quan trọng khi thiết kế hệ thống nhiều consumer.

Ứng dụng phải quyết định liệu việc các Subscriber nhìn thấy tập phần tử khác nhau có được chấp nhận hay không. Nếu tất cả consumer bắt buộc nhận cùng một tập sự kiện, không thể chọn chính sách drop tùy tiện; cần cơ chế lưu bền vững, retry hoặc xác nhận tiêu thụ phù hợp.

## 6. Buffer riêng không có nghĩa producer không bị ảnh hưởng

Buffer riêng giúp mỗi Subscriber có vùng chờ độc lập, nhưng một Subscriber chậm vẫn có thể ảnh hưởng tới producer.

| Chính sách phát | Subscriber nhanh | Subscriber chậm, buffer đầy | Hành vi producer |
| --- | --- | --- | --- |
| `submit()` | Có thể nhận phần tử | Cần tài nguyên buffer | Producer chờ cho tới khi mọi lần gửi cần thiết có thể tiếp tục |
| `offer()` | Có thể nhận phần tử | Có thể bị drop riêng | Producer tiếp tục theo chính sách drop/retry |
| `offer()` có timeout | Có thể nhận phần tử | Chờ trong giới hạn, sau đó drop/retry | Producer chờ tối đa thời hạn cấu hình |

Điều này giải thích vì sao buffer riêng không phải là cơ chế cô lập hoàn toàn. Nếu ứng dụng cần một Subscriber chậm không bao giờ làm chậm producer hoặc consumer khác, cần chọn chính sách drop, tách publisher hoặc thêm tầng lưu trữ/broker phù hợp.

## 7. Theo dõi trạng thái và hiệu năng

`SubmissionPublisher` cung cấp một số API quan sát:

| API | Ý nghĩa |
| --- | --- |
| `getMaxBufferCapacity()` | Dung lượng tối đa thực tế cho mỗi Subscriber |
| `getNumberOfSubscribers()` | Số Subscriber hiện tại |
| `hasSubscribers()` | Có Subscriber hiện tại hay không |
| `isSubscribed(subscriber)` | Subscriber cụ thể có đang đăng ký hay không |
| `getSubscribers()` | Danh sách Subscriber hiện tại để monitoring/tracking |
| `estimateMaximumLag()` | Ước lượng số phần tử đã gửi nhưng chưa được tiêu thụ lớn nhất |
| `estimateMinimumDemand()` | Ước lượng demand nhỏ nhất chưa được đáp ứng giữa các Subscriber |
| `isClosed()` | Publisher đã đóng và không nhận thêm submission hay chưa |
| `getClosedException()` | Exception gắn với lần đóng exceptional, hoặc `null` nếu chưa đóng/đóng bình thường |
| `getExecutor()` | Executor dùng để gửi dữ liệu bất đồng bộ |

~~~java
System.out.println("subscribers: " + publisher.getNumberOfSubscribers());
System.out.println("max buffer: " + publisher.getMaxBufferCapacity());
System.out.println("maximum lag estimate: " + publisher.estimateMaximumLag());
System.out.println("minimum demand estimate: " + publisher.estimateMinimumDemand());
~~~

### 7.1. Đây là số ước lượng

`estimateMaximumLag()` và `estimateMinimumDemand()` được thiết kế để monitoring. Kết quả có thể cũ hoặc không chính xác tại thời điểm đọc do các thread đang gửi và nhận dữ liệu đồng thời.

Không dùng các giá trị này để khóa luồng, quyết định rằng buffer chắc chắn còn chỗ hoặc đảm bảo một Subscriber đã xử lý xong một phần tử.

### 7.2. getSubscribers() chỉ dành cho quan sát

`getSubscribers()` trả về danh sách Subscriber hiện tại để monitoring/tracking. Không gọi trực tiếp `onNext()`, `onError()` hoặc các callback khác trên các Subscriber lấy từ danh sách đó. Hãy để `SubmissionPublisher` quản lý việc phát tín hiệu và Subscription.

## 8. Quản lý Executor và tài nguyên

`SubmissionPublisher` dùng Executor để gửi callback tới Subscriber. Executor ảnh hưởng đến mức song song, độ trễ và khả năng xử lý các Subscriber chậm.

~~~java
ExecutorService executor = Executors.newFixedThreadPool(4);
SubmissionPublisher<Event> publisher = new SubmissionPublisher<>(
    executor, Flow.defaultBufferSize()
);
~~~

### 8.1. Chọn Executor phù hợp

- Dùng pool riêng khi cần kiểm soát tài nguyên hoặc tách callback khỏi `ForkJoinPool.commonPool()`.
- Số thread phải phù hợp với số Subscriber và đặc điểm callback.
- Tránh callback `onNext()` block lâu trên pool quá nhỏ; nếu tất cả worker đều bị giữ, callback khác có thể không được thực thi.
- Không tạo một Executor mới cho từng phần tử hoặc từng lần publish.

### 8.2. Ai đóng Executor?

`SubmissionPublisher.close()` đóng Publisher và gửi tín hiệu hoàn tất; nó không tự động shutdown Executor do ứng dụng truyền vào. Nếu ứng dụng tạo Executor, ứng dụng chịu trách nhiệm quản lý vòng đời Executor.

Trình tự thường dùng:

1. Ngừng producer hoặc ngừng gửi phần tử mới.
2. Gọi `publisher.close()` hoặc `closeExceptionally(error)`.
3. Chờ Subscriber xử lý tín hiệu hoàn tất nếu ứng dụng cần xác nhận.
4. Shutdown Executor sau khi các callback cần thiết đã hoàn tất.

`close()` khi trở về không bảo đảm tất cả Subscriber đã nhận xong `onComplete()`. Nếu cần chờ, dùng `CountDownLatch`, `CompletableFuture` từ `consume()` hoặc cơ chế xác nhận riêng.

## 9. Đóng Publisher và xử lý lỗi

### 9.1. close()

`close()` báo hoàn tất bình thường, phát `onComplete()` tới các Subscriber hiện tại và từ chối các lần publish tiếp theo. Các phần tử đã được gửi cần được xử lý theo demand trước khi Subscriber nhận tín hiệu kết thúc.

~~~java
publisher.submit(event);
publisher.close();
~~~

Sau khi đóng, gọi `submit()` hoặc `offer()` sẽ gây `IllegalStateException`.

### 9.2. closeExceptionally(error)

`closeExceptionally(error)` đóng Publisher bằng lỗi và phát `onError(error)` tới Subscriber. Subscriber đăng ký sau khi Publisher đã đóng exceptional cũng nhận tín hiệu lỗi tương ứng.

~~~java
publisher.closeExceptionally(new IllegalStateException("source failed"));
~~~

Không dùng `closeExceptionally()` chỉ để thông báo một phần tử bị drop nếu Publisher vẫn có thể tiếp tục hoạt động. Drop là kết quả của một lần publish; việc kết thúc toàn bộ Publisher là quyết định khác.

### 9.3. Exception từ Subscriber

Nếu Subscriber ném exception trong `onNext()`, Subscription của Subscriber đó sẽ bị hủy. Constructor có exception handler cho phép ứng dụng nhận thông tin về lỗi `onNext()` trước khi Subscription bị hủy.

Handler constructor không thay thế việc Subscriber tự xử lý lỗi của mình. Cần phân biệt lỗi callback, lỗi Executor và lỗi producer. Nếu Executor ném `RejectedExecutionException` khi Publisher cố gắng lên lịch callback, thao tác publish có thể ném lỗi và không phải mọi Subscriber đều đã nhận phần tử đó.

### 9.4. consume() cho Subscriber đơn giản

Nếu chỉ cần chạy một `Consumer` cho từng phần tử và không cần tự viết cả bốn callback, `consume()` cung cấp cách viết gọn:

~~~java
CompletableFuture<Void> consumed = publisher.consume(item -> process(item));
~~~

Future hoàn tất bình thường khi Publisher phát `onComplete()`, và exceptional nếu Publisher phát lỗi hoặc Consumer ném exception. Đây là lựa chọn tiện lợi cho consumer đơn giản; nếu cần điều khiển demand, cancellation hoặc trạng thái chi tiết, triển khai `Subscriber` riêng.

## 10. Ví dụ hoàn chỉnh: hai Subscriber có tốc độ khác nhau

Ví dụ sau tạo một Publisher với dung lượng buffer tối đa bằng `1` cho mỗi Subscriber. Subscriber chậm nhận phần tử đầu tiên rồi tạm dừng trong callback; Subscriber nhanh tiếp tục tiêu thụ. Phần tử thứ hai lấp đầy buffer của Subscriber chậm. Khi gửi phần tử thứ ba bằng `offer()`, drop handler chỉ ghi nhận việc drop cho Subscriber chậm; Subscriber nhanh vẫn nhận được phần tử.

**Tệp:** `SubmissionPublisherBufferDemo.java`

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class SubmissionPublisherBufferDemo {
    static final class SlowSubscriber implements Flow.Subscriber<String> {
        final List<String> received = Collections.synchronizedList(new ArrayList<String>());
        final CountDownLatch subscribed;
        final CountDownLatch firstEntered;
        final CountDownLatch releaseFirst;
        final CountDownLatch done = new CountDownLatch(1);
        volatile Flow.Subscription subscription;
        volatile Throwable failure;
        volatile boolean completed;

        SlowSubscriber(CountDownLatch subscribed, CountDownLatch firstEntered,
                CountDownLatch releaseFirst) {
            this.subscribed = subscribed;
            this.firstEntered = firstEntered;
            this.releaseFirst = releaseFirst;
        }

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            subscription.request(1);
            subscribed.countDown();
        }

        @Override
        public void onNext(String item) {
            received.add(item);
            if ("first".equals(item)) {
                firstEntered.countDown();
                try {
                    releaseFirst.await();
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                    subscription.cancel();
                    failure = exception;
                    done.countDown();
                    return;
                }
            }
            subscription.request(1);
        }

        @Override
        public void onError(Throwable throwable) {
            failure = throwable;
            done.countDown();
        }

        @Override
        public void onComplete() {
            completed = true;
            done.countDown();
        }
    }

    static final class FastSubscriber implements Flow.Subscriber<String> {
        final List<String> received = Collections.synchronizedList(new ArrayList<String>());
        final CountDownLatch subscribed;
        final CountDownLatch firstTwo = new CountDownLatch(2);
        final CountDownLatch done = new CountDownLatch(1);
        volatile Throwable failure;
        volatile boolean completed;

        FastSubscriber(CountDownLatch subscribed) {
            this.subscribed = subscribed;
        }

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            subscription.request(Long.MAX_VALUE);
            subscribed.countDown();
        }

        @Override
        public void onNext(String item) {
            received.add(item);
            if ("first".equals(item) || "second".equals(item)) {
                firstTwo.countDown();
            }
        }

        @Override
        public void onError(Throwable throwable) {
            failure = throwable;
            done.countDown();
        }

        @Override
        public void onComplete() {
            completed = true;
            done.countDown();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        ExecutorService executor = Executors.newFixedThreadPool(4);
        SubmissionPublisher<String> publisher = new SubmissionPublisher<>(executor, 1);
        CountDownLatch subscribed = new CountDownLatch(2);
        CountDownLatch slowFirstEntered = new CountDownLatch(1);
        CountDownLatch releaseSlow = new CountDownLatch(1);
        SlowSubscriber slow = new SlowSubscriber(subscribed, slowFirstEntered, releaseSlow);
        FastSubscriber fast = new FastSubscriber(subscribed);
        List<String> dropped = new ArrayList<String>();

        try {
            publisher.subscribe(slow);
            publisher.subscribe(fast);
            if (!subscribed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Subscribers were not registered");
            }

            publisher.submit("first");
            if (!slowFirstEntered.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Slow subscriber did not start");
            }

            publisher.submit("second");
            if (!fast.firstTwo.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Fast subscriber did not receive first two items");
            }

            int offerStatus = publisher.offer("third", (subscriber, item) -> {
                dropped.add((subscriber == slow ? "slow" : "other") + ":" + item);
                return false;
            });
            if (offerStatus >= 0) {
                throw new IllegalStateException("Expected one subscriber buffer to reject the item");
            }

            publisher.close();
            releaseSlow.countDown();
            if (!slow.done.await(5, TimeUnit.SECONDS)
                    || !fast.done.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Subscribers did not complete");
            }
            if (slow.failure != null || fast.failure != null
                    || !slow.completed || !fast.completed) {
                throw new IllegalStateException("A subscriber did not complete normally");
            }

            System.out.println("buffer capacity: " + publisher.getMaxBufferCapacity());
            System.out.println("offer status: " + offerStatus);
            System.out.println("dropped for: " + dropped);
            System.out.println("slow received: " + slow.received);
            System.out.println("fast received: " + fast.received);
            System.out.println("slow completed: " + slow.completed);
            System.out.println("fast completed: " + fast.completed);
        } finally {
            releaseSlow.countDown();
            publisher.close();
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy với JDK 9 trở lên:

~~~text
javac --release 9 SubmissionPublisherBufferDemo.java
java SubmissionPublisherBufferDemo
~~~

Output:

~~~text
buffer capacity: 1
offer status: -1
dropped for: [slow:third]
slow received: [first, second]
fast received: [first, second, third]
slow completed: true
fast completed: true
~~~

### 10.1. Vì sao chỉ Subscriber chậm bị drop?

1. Hai Subscriber đăng ký và nhận Subscription.
2. Subscriber chậm chỉ yêu cầu một phần tử; khi nhận `first`, nó tạm dừng trong `onNext()`.
3. Publisher gửi `second`. Buffer của Subscriber chậm giữ phần tử này vì Subscriber chưa yêu cầu phần tử tiếp theo.
4. Subscriber nhanh đã tiêu thụ `first` và `second`, nên buffer riêng của nó còn chỗ.
5. `offer("third", handler)` gửi được cho Subscriber nhanh nhưng không có chỗ trong buffer của Subscriber chậm.
6. Handler ghi nhận `slow:third` và trả `false`, nên Publisher không retry cho Subscriber chậm.
7. Khi giải phóng Subscriber chậm, nó nhận `second`; sau đó cả hai Subscriber nhận `onComplete()`.

`offer status: -1` biểu thị một lần drop. Ví dụ chứng minh buffer của hai Subscriber độc lập và cho thấy một lần publish có thể thành công với Subscriber này nhưng bị drop ở Subscriber khác.

## 11. Chọn dung lượng buffer và chính sách phát

Không có một dung lượng tối ưu cho mọi hệ thống. Hãy cân nhắc:

- Số Subscriber đồng thời.
- Tốc độ producer và tốc độ xử lý trung bình/đỉnh của từng Subscriber.
- Kích thước trung bình và kích thước lớn nhất của một phần tử.
- Độ dài burst mà hệ thống cần hấp thụ.
- Mức độ chấp nhận drop.
- Chi phí bộ nhớ và thời gian chờ producer.

Buffer lớn hơn có thể hấp thụ burst lâu hơn nhưng tăng mức tiêu thụ bộ nhớ và trì hoãn thời điểm phát hiện consumer chậm. Buffer nhỏ giúp bộc lộ backpressure sớm hơn nhưng có thể khiến `submit()` chờ hoặc `offer()` drop thường xuyên.

Nếu producer liên tục nhanh hơn consumer, tăng buffer chỉ trì hoãn thời điểm bão hòa. Khi đó cần giảm tốc độ producer, tăng năng lực xử lý, chia tải hoặc lưu dữ liệu vào hệ thống bền vững.

| Yêu cầu | Chính sách phù hợp để cân nhắc |
| --- | --- |
| Không được mất sự kiện | `submit()` hoặc lưu bền vững/retry; chấp nhận backpressure |
| Producer không được chờ lâu | `offer()` không timeout với drop handler và chính sách phục hồi rõ ràng |
| Chờ buffer trong một khoảng giới hạn | `offer()` có timeout |
| Consumer chậm phải được cô lập | Buffer riêng cùng drop policy, tách Publisher hoặc broker phù hợp |
| Chỉ cần quan sát tình trạng quá tải | Lag/demand estimates và metrics; không dùng chúng làm khóa đồng bộ |

## 12. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Nghĩ tất cả Subscriber dùng chung một buffer | Hiểu sai mô hình của SubmissionPublisher | Mỗi Subscriber có buffer độc lập |
| Nghĩ buffer riêng khiến Subscriber chậm không ảnh hưởng producer | `submit()` cần tài nguyên cho mọi Subscriber hiện tại | Chọn `offer()` hoặc chính sách tách consumer nếu chấp nhận drop |
| Coi constructor capacity là tổng buffer của Publisher | Dung lượng cấu hình áp dụng cho từng Subscriber | Ước lượng bộ nhớ theo số Subscriber và buffer thực tế |
| Nghĩ `request(n)` tự tăng buffer | Demand và buffer capacity là hai cơ chế riêng | Cấu hình maximum capacity độc lập với request |
| Dùng `submit()` trên event loop | `submit()` có thể block không giới hạn khi buffer đầy | Đưa producer sang luồng phù hợp hoặc dùng offer policy |
| Dùng `offer()` nhưng bỏ qua status âm | Một số Subscriber có thể không nhận phần tử | Kiểm tra số drop và thực hiện chính sách retry/log/lưu trữ |
| Drop handler trả `true` với kỳ vọng retry vô hạn | API chỉ retry một lần | Thiết kế handler cho một lần retry và xử lý thất bại còn lại |
| Thực hiện I/O blocking trong drop handler | Các thao tác Publisher từ thread khác có thể bị chặn trong lúc handler chạy | Giữ handler ngắn, chuyển công việc nặng sang executor khác |
| Dùng lag estimate như số queue chính xác | Giá trị có thể stale hoặc không chính xác | Chỉ dùng cho monitoring |
| Shutdown Executor ngay sau `close()` | Callback hoàn tất có thể chưa chạy xong | Chờ completion rồi shutdown Executor |
| Cho rằng `close()` bảo đảm mọi Subscriber đã hoàn tất khi method return | `close()` không đợi toàn bộ callback kết thúc | Dùng latch hoặc future để xác nhận |
| Không xử lý `RejectedExecutionException` | Executor từ chối callback và không phải Subscriber nào cũng nhận phần tử | Quản lý vòng đời Executor và xử lý lỗi publish |

## 13. Quy tắc thực hành

1. Dùng constructor có Executor và maximum capacity khi cần kiểm soát tài nguyên.
2. Nhớ rằng capacity là giới hạn cho từng Subscriber; kiểm tra giá trị thực tế bằng `getMaxBufferCapacity()`.
3. Xem buffer là vùng hấp thụ burst, không phải cách giải quyết producer nhanh hơn consumer lâu dài.
4. Dùng `submit()` khi không chấp nhận drop và có thể để producer chịu backpressure.
5. Dùng `offer()` khi cần kiểm soát drop; luôn kiểm tra giá trị âm và ghi nhận Subscriber bị ảnh hưởng.
6. Chỉ trả `true` từ drop handler khi một lần retry có cơ hội thành công; API không retry vô hạn.
7. Giữ drop handler ngắn và không block.
8. Dùng lag/demand estimate để giám sát, không dùng cho đồng bộ hóa hoặc quyết định chính xác về capacity.
9. Quản lý Executor do ứng dụng tạo; chờ callback cần thiết hoàn tất trước khi shutdown.
10. Kiểm thử với Subscriber nhanh, chậm, bị lỗi và hủy đăng ký để xác nhận chính sách buffer.

## 14. Tự kiểm tra

- `SubmissionPublisher` có bao nhiêu buffer cho mỗi Subscriber? Mỗi Subscriber có một buffer độc lập.
- `maxBufferCapacity` trong constructor áp dụng cho đâu? Cho buffer của từng Subscriber.
- Dung lượng thực tế có nhất thiết bằng số truyền vào constructor không? Không; implementation có thể làm tròn hoặc giới hạn, nên dùng `getMaxBufferCapacity()`.
- `submit()` làm gì khi một Subscriber không còn chỗ trong buffer? Nó block không ngắt được cho đến khi tài nguyên cần thiết sẵn sàng.
- `offer()` có thể làm gì khi buffer một Subscriber đầy? Drop phần tử cho Subscriber đó và gọi drop handler nếu có.
- Drop handler trả `true` nghĩa là gì? Thử gửi lại đúng một lần.
- Kết quả `offer()` âm biểu thị điều gì? Số lần gửi bị drop với dấu âm.
- Buffer riêng có bảo đảm Subscriber chậm không ảnh hưởng producer không? Không; `submit()` vẫn có thể chờ vì Subscriber chậm.
- `estimateMaximumLag()` có phải số phần tử chính xác trong mọi buffer không? Không, đó là ước lượng dành cho monitoring.
- `close()` có bảo đảm mọi `onComplete()` đã chạy xong khi method trả về không? Không; cần cơ chế chờ completion nếu ứng dụng cần xác nhận.
- Ai shutdown Executor được truyền vào constructor? Ứng dụng sở hữu Executor đó.

Điểm cốt lõi: **`SubmissionPublisher` duy trì buffer riêng cho từng Subscriber; `submit()` dùng backpressure bằng cách chờ, còn `offer()` cho phép xử lý drop theo từng Subscriber.** Chọn capacity, Executor và chính sách phát theo tốc độ producer/consumer cùng yêu cầu toàn vẹn dữ liệu của ứng dụng.