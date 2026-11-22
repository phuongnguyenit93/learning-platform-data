# Hủy đăng ký và sự kiện đã được lên lịch trong Flow

Java 9 bổ sung Flow API trong package **java.util.concurrent** để xây dựng các luồng dữ liệu bất đồng bộ có kiểm soát nhu cầu (backpressure). Một Subscriber có thể dừng nhận dữ liệu bằng cách gọi **Flow.Subscription.cancel()**. Tuy nhiên, việc hủy subscription và việc dừng một tác vụ đã được lên lịch là hai thao tác có vòng đời riêng.

Điểm cần nhớ là cancel() yêu cầu Publisher dần ngừng gửi tín hiệu đến Subscriber đó. Nó không đảm bảo mọi tín hiệu đang chờ biến mất ngay lập tức. Nếu Publisher tự dùng ScheduledExecutorService để phát sự kiện định kỳ, Subscriber hủy subscription cũng không tự dừng tác vụ định kỳ của Publisher.

## 1. Các thành phần trong Flow API

Flow API mô hình hóa một luồng dữ liệu qua bốn thành phần:

| Thành phần | Vai trò |
|---|---|
| Flow.Publisher<T> | Nguồn phát các phần tử T đến Subscriber |
| Flow.Subscriber<T> | Thành phần nhận và xử lý phần tử |
| Flow.Subscription | Liên kết một Publisher với một Subscriber, quản lý demand và cancellation |
| Flow.Processor<T,R> | Vừa nhận dữ liệu như Subscriber, vừa phát dữ liệu như Publisher |

Vòng đời thông thường:

1. Subscriber gọi publisher.subscribe(subscriber).
2. Publisher gọi subscriber.onSubscribe(subscription).
3. Subscriber gọi subscription.request(n) để báo số phần tử muốn nhận.
4. Publisher phát các phần tử qua onNext(item) theo demand.
5. Luồng có thể kết thúc bằng onComplete() hoặc lỗi bằng onError(error).
6. Subscriber có thể gọi subscription.cancel() khi không còn muốn nhận dữ liệu.

Các interface Flow tương ứng với mô hình Reactive Streams và có từ Java 9. request(n) là cơ chế backpressure: Subscriber kiểm soát lượng dữ liệu được yêu cầu, giúp Publisher tránh đẩy dữ liệu vô hạn vào một Subscriber xử lý chậm.

## 2. Subscription.cancel() làm gì?

Flow.Subscription.cancel() yêu cầu Publisher ngừng gửi thông điệp đến Subscriber tương ứng:

~~~java
subscription.cancel();
~~~

Phương thức trả về void. Nó không tạo một subscription mới và cũng không đóng toàn bộ Publisher.

Một subscription đại diện cho quan hệ giữa một Subscriber cụ thể và Publisher. Vì vậy:

- Hủy một subscription chỉ dừng việc phân phối đến Subscriber đó.
- Những Subscriber khác của cùng Publisher vẫn có thể tiếp tục nhận dữ liệu.
- Subscriber nên gọi cancel() trên subscription mà Publisher đã truyền vào onSubscribe().
- Có thể gọi cancel() khi không còn cần dữ liệu, ví dụ sau khi đã nhận đủ số phần tử cần thiết hoặc khi người dùng yêu cầu dừng.

Không dùng request(0) để hủy. Theo Flow API, request với số lượng nhỏ hơn hoặc bằng 0 khiến Subscriber nhận onError() với IllegalArgumentException. Muốn dừng nhận dữ liệu, hãy gọi cancel().

## 3. Hủy subscription không có nghĩa là dừng ngay mọi tín hiệu

Đây là chi tiết quan trọng nhất của chủ đề.

Theo Javadoc Java 9, cancel() có hiệu lực theo hướng eventual và best-effort. **Publisher có thể vẫn gửi thêm thông điệp sau khi Subscriber gọi cancel().** Một subscription đã hủy cũng không bắt buộc phải nhận onComplete() hoặc onError().

Điều này xảy ra vì khi cancel() được gọi:

- Một lần gọi onNext() có thể đang chạy.
- Một tín hiệu có thể đã được xếp hàng trong buffer hoặc executor.
- Publisher có thể chưa xử lý xong yêu cầu hủy.
- Tác vụ phát dữ liệu có thể đã bắt đầu trước thời điểm hủy.

Vì vậy, không được giả định rằng sau dòng subscription.cancel() thì callback onNext() không thể chạy thêm lần nào. Subscriber cần xử lý an toàn các callback đang bay hoặc đã được lên lịch, nhất là khi chúng truy cập tài nguyên sắp được giải phóng.

Ví dụ, nếu Subscriber hủy sau phần tử thứ ba:

~~~java
public void onNext(Integer item) {
    if (++received == 3) {
        subscription.cancel();
    }
}
~~~

Đoạn code yêu cầu Publisher ngừng gửi về sau. Tuy nhiên, một tín hiệu đã được phát hoặc đang chờ vẫn có thể đến. Nếu logic xử lý có trạng thái, hãy bảo vệ việc đóng tài nguyên và các thao tác dọn dẹp để không bị thực hiện lặp hoặc truy cập tài nguyên đã đóng.

Sau khi hủy, Subscriber không nên trông đợi onComplete() như một xác nhận hủy. Nếu ứng dụng cần xác nhận nội bộ rằng yêu cầu dừng đã được phát đi, hãy tự quản lý trạng thái hoặc dùng cơ chế đồng bộ riêng.

## 4. Hủy từ onSubscribe() hoặc onNext()

Subscriber nhận Flow.Subscription trong onSubscribe(). Có thể lưu subscription để dùng trong những callback tiếp theo:

~~~java
class LimitedSubscriber implements Flow.Subscriber<Integer> {
    private Flow.Subscription subscription;
    private int received;

    @Override
    public void onSubscribe(Flow.Subscription subscription) {
        this.subscription = subscription;
        subscription.request(Long.MAX_VALUE);
    }

    @Override
    public void onNext(Integer item) {
        System.out.println("Received: " + item);

        if (++received == 3) {
            subscription.cancel();
        }
    }

    @Override
    public void onError(Throwable error) {
        error.printStackTrace();
    }

    @Override
    public void onComplete() {
        System.out.println("Completed");
    }
}
~~~

Trong ví dụ, Subscriber yêu cầu lượng dữ liệu không giới hạn thực tế bằng Long.MAX_VALUE, sau đó chủ động hủy khi nhận đủ ba phần tử.

Một lựa chọn khác là yêu cầu theo từng đợt nhỏ. Ví dụ, Subscriber chỉ gọi request(1) trong onSubscribe() và yêu cầu thêm một phần tử sau khi xử lý xong mỗi onNext(). Cách này giúp kiểm soát lượng dữ liệu đang chờ và phù hợp khi xử lý mỗi phần tử tốn nhiều thời gian.

Không nên gọi các phương thức của Subscriber trực tiếp từ Publisher để thay thế giao thức Flow. Publisher phải phát tín hiệu theo subscription và tuân thủ thứ tự callback của từng Subscriber.

## 5. Sự kiện đã được lên lịch là một tác vụ riêng

Một Publisher có thể tự tạo sự kiện theo chu kỳ bằng ScheduledExecutorService, ví dụ phát trạng thái hệ thống mỗi giây:

~~~java
ScheduledExecutorService scheduler =
        Executors.newSingleThreadScheduledExecutor();

ScheduledFuture<?> periodicTask =
        scheduler.scheduleAtFixedRate(
                () -> publisher.submit(nextEvent()),
                0,
                1,
                TimeUnit.SECONDS
        );
~~~

ScheduledExecutorService trả về ScheduledFuture<?> khi lên lịch tác vụ. Đối tượng này quản lý vòng đời của chính tác vụ đã lên lịch.

Muốn dừng tác vụ định kỳ, phải hủy ScheduledFuture:

~~~java
periodicTask.cancel(false);
scheduler.shutdown();
~~~

Ý nghĩa:

- periodicTask.cancel(false) ngăn các lần chạy tiếp theo; nếu một lần chạy đã bắt đầu, lần đó được phép hoàn tất.
- periodicTask.cancel(true) yêu cầu ngắt thread đang chạy nếu có thể. Đây chỉ là nỗ lực interrupt, không đảm bảo tác vụ dừng tức thì nếu code không phản hồi interruption.
- scheduler.shutdown() ngừng nhận tác vụ mới và cho phép các tác vụ đang chạy hoàn tất.
- Có thể dùng awaitTermination() nếu cần đợi scheduler kết thúc trước khi giải phóng tài nguyên liên quan.

**Hủy Flow.Subscription không hủy ScheduledFuture.** Nếu Subscriber ngừng nhận dữ liệu nhưng Publisher vẫn còn tác vụ định kỳ, tác vụ đó có thể tiếp tục chạy và gọi submit() dù Subscriber đã rời luồng.

Ngược lại, hủy ScheduledFuture chỉ dừng tác vụ phát sự kiện đã lên lịch. Nó không tự hủy các subscription khác hoặc gửi tín hiệu kết thúc cho toàn bộ Subscriber.

## 6. Dừng một Publisher định kỳ đúng thứ tự

SubmissionPublisher<T> là Publisher có sẵn trong Java 9, hỗ trợ phát dữ liệu bất đồng bộ qua Executor và buffer riêng cho từng Subscriber.

Nếu một lớp Publisher sở hữu tác vụ định kỳ, nên quản lý cả ba tài nguyên:

1. ScheduledFuture đại diện cho tác vụ phát sự kiện.
2. ScheduledExecutorService thực thi tác vụ định kỳ.
3. SubmissionPublisher phân phối sự kiện đến Subscriber.

Khi dừng toàn bộ Publisher định kỳ, thứ tự nên là:

1. Hủy ScheduledFuture để ngăn các lần phát mới.
2. Shutdown scheduler và đợi lần chạy đang hoạt động hoàn tất nếu cần.
3. Gọi SubmissionPublisher.close() để không nhận thêm submission và gửi onComplete() đến các Subscriber còn đang hoạt động.

Ví dụ lớp Publisher quản lý tác vụ định kỳ:

~~~java
class PeriodicPublisher<T> extends SubmissionPublisher<T> {
    private final ScheduledExecutorService scheduler =
            Executors.newSingleThreadScheduledExecutor();
    private final ScheduledFuture<?> periodicTask;

    PeriodicPublisher(
            Executor executor,
            int maxBufferCapacity,
            Supplier<? extends T> supplier,
            long period,
            TimeUnit unit) {
        super(executor, maxBufferCapacity);

        periodicTask = scheduler.scheduleAtFixedRate(
                () -> submit(supplier.get()),
                0,
                period,
                unit
        );
    }

    @Override
    public void close() {
        periodicTask.cancel(false);
        scheduler.shutdown();

        try {
            scheduler.awaitTermination(5, TimeUnit.SECONDS);
        } catch (InterruptedException exception) {
            scheduler.shutdownNow();
            Thread.currentThread().interrupt();
        }

        super.close();
    }
}
~~~

Ví dụ này thể hiện hai cấp dừng khác nhau: cancel ScheduledFuture để ngừng nguồn phát định kỳ và close Publisher để kết thúc luồng phân phối. Trong ứng dụng thực tế, cần chọn thời gian chờ phù hợp và xử lý trường hợp scheduler chưa kết thúc trong thời hạn chờ.

Nếu chỉ một Subscriber rời luồng, không nên đóng Publisher dùng chung cho mọi Subscriber. Hãy chỉ hủy subscription của Subscriber đó; giữ tác vụ định kỳ nếu những Subscriber khác vẫn cần dữ liệu.

## 7. close(), closeExceptionally() và cancel() khác nhau

Ba thao tác có phạm vi khác nhau:

| Thao tác | Phạm vi | Kết quả |
|---|---|---|
| subscription.cancel() | Một quan hệ Subscriber–Publisher | Publisher dần ngừng gửi dữ liệu cho Subscriber đó; tín hiệu đang chờ vẫn có thể đến |
| publisher.close() | Toàn bộ SubmissionPublisher | Ngừng nhận submission mới và gửi onComplete() đến Subscriber còn hoạt động |
| publisher.closeExceptionally(error) | Toàn bộ SubmissionPublisher | Ngừng nhận submission mới và gửi onError(error) đến Subscriber còn hoạt động |

close() không thay thế việc hủy tác vụ định kỳ. Nếu một ScheduledFuture vẫn chạy và tiếp tục gọi submit() sau khi Publisher đóng, lần submit tiếp theo có thể ném IllegalStateException.

Vì vậy, Publisher sở hữu lịch phát dữ liệu cần hủy tác vụ định kỳ trước khi gọi close(). Nếu Subscriber đã cancel(), không được trông đợi Subscriber đó nhận được onComplete() từ thao tác close sau này.

## 8. Ví dụ hoàn chỉnh: Subscriber hủy nhưng Publisher vẫn phát theo lịch

Chương trình dưới đây cho thấy hai vòng đời độc lập:

- Subscriber hủy subscription sau khi nhận ba phần tử.
- Tác vụ định kỳ của Publisher vẫn tiếp tục phát thêm sự kiện.
- Chỉ khi gọi close(), lớp Publisher mới hủy tác vụ định kỳ, shutdown scheduler và đóng SubmissionPublisher.

Lưu chương trình dưới tên **FlowCancellationDemo.java**.

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledFuture;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class FlowCancellationDemo {

    private static final class PeriodicPublisher
            extends SubmissionPublisher<Integer> {
        private final ScheduledExecutorService scheduler =
                Executors.newSingleThreadScheduledExecutor();
        private final AtomicInteger sequence = new AtomicInteger();
        private final AtomicBoolean subscriptionCancelled =
                new AtomicBoolean();
        private final CountDownLatch postCancelPublications =
                new CountDownLatch(2);
        private final ScheduledFuture<?> periodicTask;

        PeriodicPublisher() {
            periodicTask = scheduler.scheduleAtFixedRate(() -> {
                submit(sequence.incrementAndGet());
                if (subscriptionCancelled.get()) {
                    postCancelPublications.countDown();
                }
            }, 0, 20, TimeUnit.MILLISECONDS);
        }

        void markSubscriptionCancelled() {
            subscriptionCancelled.set(true);
        }

        boolean awaitPostCancelPublications() throws InterruptedException {
            return postCancelPublications.await(5, TimeUnit.SECONDS);
        }

        boolean isScheduledTaskCancelled() {
            return periodicTask.isCancelled();
        }

        @Override
        public void close() {
            periodicTask.cancel(false);
            scheduler.shutdown();
            try {
                if (!scheduler.awaitTermination(5, TimeUnit.SECONDS)) {
                    scheduler.shutdownNow();
                }
            } catch (InterruptedException exception) {
                scheduler.shutdownNow();
                Thread.currentThread().interrupt();
            }
            super.close();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        PeriodicPublisher publisher = new PeriodicPublisher();
        CountDownLatch cancellationRequested = new CountDownLatch(1);
        AtomicBoolean receivedError = new AtomicBoolean();

        publisher.subscribe(new Flow.Subscriber<Integer>() {
            private Flow.Subscription subscription;
            private int received;

            @Override
            public void onSubscribe(Flow.Subscription subscription) {
                this.subscription = subscription;
                subscription.request(Long.MAX_VALUE);
            }

            @Override
            public void onNext(Integer item) {
                if (++received == 3) {
                    subscription.cancel();
                    publisher.markSubscriptionCancelled();
                    cancellationRequested.countDown();
                }
            }

            @Override
            public void onError(Throwable throwable) {
                receivedError.set(true);
                cancellationRequested.countDown();
            }

            @Override
            public void onComplete() {
            }
        });

        boolean cancelled =
                cancellationRequested.await(5, TimeUnit.SECONDS);
        boolean producerContinued = cancelled
                && publisher.awaitPostCancelPublications();

        publisher.close();

        if (!cancelled || !producerContinued || receivedError.get()) {
            throw new IllegalStateException(
                    "Flow cancellation demo did not complete as expected");
        }

        System.out.println(
                "subscription cancellation requested: " + cancelled);
        System.out.println(
                "scheduled publisher continued after cancellation: "
                        + producerContinued);
        System.out.println(
                "scheduled task cancelled: "
                        + publisher.isScheduledTaskCancelled());
        System.out.println(
                "publisher closed: " + publisher.isClosed());
    }
}
~~~

Biên dịch và chạy trên Java 9 trở lên:

~~~bash
javac --release 9 FlowCancellationDemo.java
java FlowCancellationDemo
~~~

Kết quả stdout:

~~~text
subscription cancellation requested: true
scheduled publisher continued after cancellation: true
scheduled task cancelled: true
publisher closed: true
~~~

Hai dòng đầu xác nhận việc hủy subscription không tự dừng bộ lập lịch của Publisher. Hai dòng cuối xác nhận close() đã hủy tác vụ định kỳ và đóng SubmissionPublisher.

Chương trình không in từng phần tử vì callback có thể chạy bất đồng bộ và Flow cho phép một số tín hiệu đang bay đến sau khi cancel() được gọi. Ví dụ chỉ kiểm tra các trạng thái vòng đời để kết quả chạy ổn định.

## 9. Lỗi thường gặp và cách tránh

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Nghĩ cancel() dừng mọi callback ngay lập tức | Bỏ qua tín hiệu đang bay hoặc đã xếp hàng | Chuẩn bị xử lý an toàn callback sau yêu cầu hủy |
| Chờ onComplete() sau khi cancel() | Có thể chờ mãi vì subscription đã hủy không bắt buộc nhận tín hiệu kết thúc | Tự quản lý trạng thái hủy hoặc dùng latch/cơ chế xác nhận riêng |
| Hủy subscription nhưng quên ScheduledFuture | Tác vụ định kỳ vẫn chạy và tiếp tục tạo sự kiện | Lưu ScheduledFuture và gọi cancel() khi dừng nguồn phát |
| Đóng SubmissionPublisher trước khi dừng tác vụ định kỳ | Tác vụ có thể gọi submit() sau close() và gặp IllegalStateException | Hủy tác vụ, đợi lần chạy hiện tại hoàn tất, rồi close Publisher |
| Gọi publisher.close() khi chỉ một Subscriber muốn rời luồng | Các Subscriber khác cũng bị kết thúc | Chỉ hủy subscription của Subscriber cần rời luồng |
| Dùng request(0) để dừng nhận dữ liệu | Subscriber nhận onError với IllegalArgumentException | Dùng subscription.cancel() |
| Giả định cancel(false) ngắt tác vụ đang chạy | Lần chạy hiện tại vẫn có thể tiếp tục | Chờ tác vụ hoàn tất hoặc dùng cancel(true) khi tác vụ hỗ trợ interrupt |
| Giải phóng tài nguyên ngay sau cancel() | Callback đang bay có thể truy cập tài nguyên đã đóng | Đồng bộ quá trình dừng và làm thao tác dọn dẹp an toàn khi gọi lặp |

## 10. Ghi nhớ

- Flow API được bổ sung từ Java 9 và dùng Publisher, Subscriber, Subscription, Processor để trao đổi dữ liệu có backpressure.
- Subscriber gọi request(n) để yêu cầu dữ liệu và cancel() để yêu cầu ngừng nhận.
- cancel() có hiệu lực eventual, best-effort; tín hiệu đang chờ có thể vẫn đến sau khi gọi.
- Subscription đã hủy không bắt buộc nhận onComplete() hoặc onError().
- Hủy subscription chỉ ảnh hưởng một Subscriber; nó không tự dừng Publisher hoặc ScheduledFuture.
- Muốn dừng tác vụ phát định kỳ, phải hủy ScheduledFuture và shutdown ScheduledExecutorService.
- Với SubmissionPublisher, hãy dừng tác vụ tạo dữ liệu trước, rồi gọi close() để kết thúc Publisher.
- Chỉ đóng Publisher dùng chung khi muốn kết thúc luồng cho tất cả Subscriber còn hoạt động.
- Thiết kế callback và cleanup để chịu được trạng thái cạnh tranh giữa cancel(), tín hiệu đang bay và tác vụ đã được lên lịch.

## Tài liệu tham khảo

- [Flow.Subscription — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/util/concurrent/Flow.Subscription.html)
- [Flow — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/util/concurrent/Flow.html)
- [SubmissionPublisher — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/util/concurrent/SubmissionPublisher.html)
- [ScheduledExecutorService — Java SE 9 API](https://docs.oracle.com/javase/9/docs/api/java/util/concurrent/ScheduledExecutorService.html)
