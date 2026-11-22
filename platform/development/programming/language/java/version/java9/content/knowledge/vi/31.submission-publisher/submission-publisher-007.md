# Xử lý ngoại lệ do Subscriber

Trong Flow, Subscriber nhận dữ liệu qua các callback như onSubscribe, onNext, onError và onComplete. Các callback này là điểm giao tiếp giữa Publisher và code xử lý của ứng dụng. Nếu một callback tự ném exception, Publisher không thể xem đó là một tín hiệu lỗi bình thường để tiếp tục luồng.

Hợp đồng Reactive Streams yêu cầu các callback của Subscriber phải trả về bình thường. Khi Subscriber không thể xử lý một phần tử, cách báo hiệu hợp lệ là hủy Subscription bằng cancel và chuyển lỗi sang cơ chế xử lý của ứng dụng. Với SubmissionPublisher của Java 9, một exception thoát khỏi bất kỳ callback Subscriber nào làm hủy subscription tương ứng. Constructor của SubmissionPublisher còn cho phép đăng ký handler riêng cho exception phát sinh trong onNext.

## 1. Phân biệt lỗi của Publisher và lỗi trong Subscriber

Hai tình huống có ý nghĩa khác nhau:

| Tình huống | Ý nghĩa | Cách xử lý |
|---|---|---|
| Publisher không thể tiếp tục phát dữ liệu | Lỗi thuộc nguồn phát hoặc pipeline phía Publisher | Publisher gửi onError |
| Subscriber ném exception trong callback | Consumer vi phạm hợp đồng callback | Subscription của Subscriber bị hủy; runtime hoặc Publisher implementation ghi nhận lỗi |
| Subscriber chủ động không muốn nhận thêm | Không phải lỗi | Subscriber gọi Subscription.cancel() |

Ví dụ Publisher kết thúc bất thường:

~~~java
publisher.closeExceptionally(
        new IllegalStateException("source failed")
);
~~~

Subscriber nhận onError vì Publisher thông báo nguồn phát thất bại.

Ngược lại, nếu onNext của Subscriber ném IllegalStateException, đó là lỗi trong code tiêu thụ dữ liệu. Không nên xem việc ném exception như cách yêu cầu Publisher phát onError cho chính Subscriber đó. Subscriber cần tự xử lý lỗi và hủy subscription khi không thể tiếp tục.

## 2. Quy tắc callback phải trả về bình thường

Reactive Streams Specification, quy tắc Subscriber 2.13, yêu cầu onSubscribe, onNext, onError và onComplete phải trả về bình thường. Ngoại lệ duy nhất là tham số null có thể dẫn đến NullPointerException theo hợp đồng. Cách hợp lệ để Subscriber báo rằng nó không thể tiếp tục là hủy Subscription.

Nếu callback ném exception:

- Subscription liên quan phải được xem như đã bị hủy.
- Bên gọi callback phải báo cáo tình trạng lỗi theo cách phù hợp với runtime.
- Subscriber không được giả định Publisher sẽ tiếp tục gửi dữ liệu.
- Subscriber không được dùng exception thoát khỏi callback như một cơ chế retry hoặc recovery.

Quy tắc này giúp Publisher không phải đoán cách xử lý một Subscriber đã rơi khỏi callback giữa chừng. Subscriber nên giữ lỗi trong phạm vi callback, quyết định có thể phục hồi hay không, rồi kết thúc hoặc tiếp tục theo hợp đồng.

## 3. SubmissionPublisher xử lý exception như thế nào?

SubmissionPublisher là implementation Flow.Publisher có sẵn từ Java 9. Theo API documentation:

- Nếu bất kỳ phương thức Subscriber nào ném exception, subscription của Subscriber đó bị hủy.
- Nếu constructor nhận một handler, handler được gọi trước khi hủy khi exception phát sinh trong onNext.
- Handler này không được dùng để xử lý exception trong onSubscribe, onError hoặc onComplete. Các exception ở những callback đó không được ghi nhận hoặc xử lý bởi handler này trước khi hủy.
- Handler không làm cho Subscriber tự động đăng ký lại hoặc tiếp tục nhận dữ liệu.

Constructor có handler:

~~~java
SubmissionPublisher(
        Executor executor,
        int maxBufferCapacity,
        BiConsumer<? super Flow.Subscriber<? super T>,
                   ? super Throwable> handler
)
~~~

Handler nhận hai tham số: Subscriber gây ra exception và Throwable đã được ném. Đây là nơi phù hợp để ghi log, tăng metric, gắn mã subscriber hoặc gửi cảnh báo. Nên giữ handler ngắn, không thực hiện công việc chặn lâu và tránh để handler tự ném exception.

Nếu không cần handler riêng, có thể dùng constructor không có handler. Khi đó SubmissionPublisher vẫn hủy subscription bị lỗi, nhưng ứng dụng không có callback riêng để ghi nhận exception trong onNext.

## 4. Handler chỉ dành cho onNext

Ví dụ đăng ký handler:

~~~java
SubmissionPublisher<Integer> publisher =
        new SubmissionPublisher<>(
                executor,
                32,
                (subscriber, error) -> {
                    logger.error(
                            "Subscriber {} failed",
                            subscriber,
                            error
                    );
                }
        );
~~~

Khi onNext ném exception, handler được gọi trước khi subscription bị hủy. Handler có thể ghi nhận:

- Loại exception và stack trace.
- Subscriber gây ra lỗi.
- Mã correlation hoặc thông tin nghiệp vụ liên quan.
- Số lần callback lỗi để theo dõi chất lượng consumer.

Handler không phải nơi sửa dữ liệu rồi phát lại cho Subscriber. Sau lỗi, subscription đó đã đi vào quá trình hủy. Nếu muốn thử lại dữ liệu, cần thiết kế retry ở tầng nghiệp vụ hoặc tạo một subscription/pipeline mới có chính sách rõ ràng.

Handler không áp dụng cho exception trong onSubscribe, onError hoặc onComplete. Đừng dựa vào constructor handler như một bộ bắt lỗi tổng quát cho mọi callback.

## 5. Xử lý lỗi ngay trong Subscriber

Nếu lỗi có thể được xử lý tại chỗ, hãy bắt nó trong callback. Khi xử lý không thể tiếp tục, hủy subscription và chuyển lỗi sang cơ chế của ứng dụng:

~~~java
final class ProcessingSubscriber implements Flow.Subscriber<Event> {
    private Flow.Subscription subscription;

    @Override
    public void onSubscribe(Flow.Subscription subscription) {
        this.subscription = subscription;
        subscription.request(1);
    }

    @Override
    public void onNext(Event event) {
        try {
            process(event);
            subscription.request(1);
        } catch (RuntimeException error) {
            subscription.cancel();
            reportProcessingFailure(event, error);
        }
    }

    @Override
    public void onError(Throwable error) {
        reportPublisherFailure(error);
    }

    @Override
    public void onComplete() {
        finishProcessing();
    }
}
~~~

Trong ví dụ, Subscriber chỉ request thêm một phần tử sau khi xử lý thành công phần tử hiện tại. Nếu xử lý thất bại, nó cancel và báo lỗi ra ngoài. Cách này giữ lỗi trong phạm vi ứng dụng và tránh để exception thoát khỏi callback.

Nếu lỗi là lỗi có thể phục hồi, hãy định nghĩa chính sách cụ thể: bỏ qua item, đưa item vào dead-letter queue, retry có giới hạn hoặc dừng subscription. Không tự động request thêm khi trạng thái xử lý trước đó chưa rõ ràng.

## 6. Xử lý từng callback đúng cách

**onSubscribe**

Lưu Subscription và thiết lập demand. Nếu khởi tạo tài nguyên hoặc cấu hình consumer có thể lỗi, hãy bắt exception, cancel subscription và báo lỗi ra tầng ứng dụng. Không để exception khởi tạo thoát khỏi onSubscribe.

**onNext**

Đây là callback xử lý từng item và là nơi SubmissionPublisher có thể gọi handler đã đăng ký. Bắt các exception dự kiến quanh phần xử lý nghiệp vụ. Nếu không thể tiếp tục, cancel subscription; không tiếp tục request như thể item đã được xử lý thành công.

**onError**

Đây là tín hiệu terminal do Publisher gửi. Ghi nhận lỗi, hoàn tất cleanup và thông báo tầng gọi. Exception ném ra từ onError không được handler onNext của SubmissionPublisher xử lý. Không dùng onError để request thêm dữ liệu hoặc tiếp tục subscription đã kết thúc.

**onComplete**

Đây là tín hiệu kết thúc bình thường. Hoàn tất tài nguyên và trạng thái nghiệp vụ. Exception ném ra từ onComplete cũng không được handler onNext xử lý. Vì đây là callback terminal, hãy bắt lỗi cleanup bên trong callback nếu cần báo cáo mà không để exception thoát ra.

## 7. Một Subscriber lỗi không nhất thiết làm hỏng các Subscriber khác

SubmissionPublisher quản lý subscription riêng cho từng Subscriber. Nếu một Subscriber ném exception trong callback, subscription của Subscriber đó bị hủy. Các Subscriber khác vẫn có thể tiếp tục nhận item nếu Publisher và executor còn hoạt động bình thường.

Điều này hữu ích khi cùng một Publisher phục vụ nhiều consumer độc lập. Một consumer lỗi không nên khiến toàn bộ hệ thống dừng theo mặc định. Tuy nhiên, lỗi ở executor, drop handler hoặc chính Publisher có thể ảnh hưởng việc phát dữ liệu; cần phân biệt chúng với lỗi callback của một Subscriber.

Không nên dùng một Subscriber instance để đăng ký nhiều lần nhằm thay thế subscription đã hủy. Tạo instance mới và xác định rõ điểm tiếp tục dữ liệu nếu nghiệp vụ cần khôi phục.

## 8. Kiểm thử exception của Subscriber

Một bài kiểm thử tốt nên xác nhận các điều kiện:

- Handler được gọi khi onNext ném exception.
- Subscription của Subscriber lỗi bị hủy.
- Handler không được gọi cho exception trong onComplete, onError hoặc onSubscribe.
- Subscriber khỏe khác vẫn nhận được các item tiếp theo.
- Exception và Subscriber được handler nhận diện đúng.
- Test chờ callback bằng CountDownLatch hoặc Future, không dùng Thread.sleep để đoán thời điểm.

Khi kiểm thử bất đồng bộ, nên dùng executor riêng và latch để đồng bộ. Tránh dựa vào việc callback chạy ngay trên thread gọi submit; SubmissionPublisher được thiết kế để phân phối bất đồng bộ.

## 9. Ví dụ chạy được với Java 17+

Tạo file **SubscriberExceptionDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class SubscriberExceptionDemo {
    static class BrokenSubscriber implements Flow.Subscriber<Integer> {
        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            subscription.request(Long.MAX_VALUE);
        }

        @Override
        public void onNext(Integer item) {
            throw new IllegalStateException("consumer failed");
        }

        @Override
        public void onError(Throwable error) {
        }

        @Override
        public void onComplete() {
        }
    }

    static class HealthySubscriber implements Flow.Subscriber<Integer> {
        final List<Integer> items = new ArrayList<>();
        final CountDownLatch completed = new CountDownLatch(1);

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            subscription.request(Long.MAX_VALUE);
        }

        @Override
        public void onNext(Integer item) {
            items.add(item);
        }

        @Override
        public void onError(Throwable error) {
            throw new AssertionError("Unexpected publisher failure", error);
        }

        @Override
        public void onComplete() {
            completed.countDown();
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try {
            AtomicInteger handlerCalls = new AtomicInteger();
            CountDownLatch handlerCalled = new CountDownLatch(1);
            BrokenSubscriber broken = new BrokenSubscriber();
            HealthySubscriber healthy = new HealthySubscriber();

            try (SubmissionPublisher<Integer> publisher =
                         new SubmissionPublisher<>(
                                 executor,
                                 8,
                                 (subscriber, error) -> {
                                     handlerCalls.incrementAndGet();
                                     System.out.println("onNext handler: "
                                             + error.getClass().getSimpleName());
                                     handlerCalled.countDown();
                                 })) {
                publisher.subscribe(broken);
                publisher.subscribe(healthy);
                publisher.submit(1);
                publisher.submit(2);
                publisher.close();

                if (!handlerCalled.await(5, TimeUnit.SECONDS)
                        || !healthy.completed.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "subscriber callback timed out"
                    );
                }

                System.out.println("broken subscribed: "
                        + publisher.isSubscribed(broken));
                System.out.println("healthy items: " + healthy.items);
                System.out.println("onNext handler calls: "
                        + handlerCalls.get());
            }

            AtomicInteger terminalHandlerCalls = new AtomicInteger();
            CountDownLatch terminalCallback = new CountDownLatch(1);
            try (SubmissionPublisher<Integer> publisher =
                         new SubmissionPublisher<>(
                                 executor,
                                 8,
                                 (subscriber, error) ->
                                         terminalHandlerCalls.incrementAndGet())) {
                publisher.subscribe(new Flow.Subscriber<Integer>() {
                    @Override
                    public void onSubscribe(Flow.Subscription subscription) {
                        subscription.request(Long.MAX_VALUE);
                    }

                    @Override
                    public void onNext(Integer item) {
                    }

                    @Override
                    public void onError(Throwable error) {
                    }

                    @Override
                    public void onComplete() {
                        try {
                            throw new IllegalStateException(
                                    "completion callback failed"
                            );
                        } finally {
                            terminalCallback.countDown();
                        }
                    }
                });
                publisher.close();

                if (!terminalCallback.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("onComplete timed out");
                }
                System.out.println("onComplete handler calls: "
                        + terminalHandlerCalls.get());
            }
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac SubscriberExceptionDemo.java
java SubscriberExceptionDemo
~~~

Kết quả stdout:

~~~text
onNext handler: IllegalStateException
broken subscribed: false
healthy items: [1, 2]
onNext handler calls: 1
onComplete handler calls: 0
~~~

Giải thích:

- BrokenSubscriber ném IllegalStateException trong onNext.
- Handler của SubmissionPublisher nhận exception trước khi subscription bị hủy.
- isSubscribed trả về false cho Subscriber lỗi.
- HealthySubscriber vẫn nhận cả hai item và hoàn tất bình thường.
- Subscriber ném exception trong onComplete, nhưng handler dành cho onNext không được gọi.

Ví dụ dùng CountDownLatch để đợi callback bất đồng bộ và dùng executor riêng theo đúng mô hình SubmissionPublisher. Nó không dựa vào Thread.sleep hoặc thứ tự thực thi ngẫu nhiên.

## 10. Lỗi thường gặp

**Ném exception ra khỏi onNext để yêu cầu onError:** đây là vi phạm hợp đồng callback. Hãy bắt lỗi, cancel và báo lỗi qua cơ chế ứng dụng.

**Cho rằng handler xử lý mọi callback:** handler constructor của SubmissionPublisher chỉ áp dụng cho exception trong onNext.

**Cho rằng handler có thể phục hồi subscription:** handler được gọi trước khi hủy; nó không làm subscription hoạt động trở lại.

**Không cancel khi Subscriber không thể tiếp tục:** nếu không còn xử lý dữ liệu, phải hủy subscription thay vì bỏ qua hoặc tiếp tục request.

**Để exception cleanup thoát khỏi onComplete/onError:** các callback terminal cũng phải trả về bình thường; bắt và báo cáo lỗi cleanup bên trong.

**Nhầm lỗi Publisher với lỗi Subscriber:** closeExceptionally báo lỗi nguồn phát; exception trong callback là lỗi consumer.

**Dùng một Subscriber đã lỗi để subscribe lại:** tạo Subscriber mới và xác định rõ chính sách tiếp tục dữ liệu.

**Bỏ qua log/metric của callback exception:** nếu không ghi nhận, lỗi consumer có thể âm thầm làm mất một subscription.

## 11. Checklist

- Giữ onSubscribe, onNext, onError và onComplete không ném exception ra ngoài.
- Bắt lỗi xử lý dự kiến ngay trong callback.
- Khi không thể tiếp tục, gọi Subscription.cancel().
- Dùng handler constructor của SubmissionPublisher để quan sát exception trong onNext.
- Không trông đợi handler xử lý onSubscribe, onError hoặc onComplete.
- Không xem handler là cơ chế retry hoặc phục hồi subscription.
- Phân biệt lỗi Publisher với lỗi Subscriber.
- Kiểm tra subscription lỗi đã bị hủy và Subscriber khác vẫn hoạt động.
- Dùng latch hoặc future để đồng bộ bài kiểm thử bất đồng bộ.
- Ghi log và metric đủ để truy vết Subscriber gây lỗi.

Hợp đồng Flow yêu cầu callback của Subscriber trả về bình thường. Với SubmissionPublisher, exception trong callback làm hủy subscription tương ứng; handler tùy chọn chỉ cung cấp điểm quan sát exception trong onNext. Thiết kế Subscriber tự bắt lỗi, cancel khi cần và báo cáo qua tầng ứng dụng giúp pipeline giữ đúng giao thức và cô lập consumer lỗi.

## Tài liệu tham khảo

- Java SE API: SubmissionPublisher — https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html
- Reactive Streams Specification — https://github.com/reactive-streams/reactive-streams-jvm
