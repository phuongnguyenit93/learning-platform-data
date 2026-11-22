# Quan sát độ trễ và nhu cầu ước lượng với SubmissionPublisher

## 1. SubmissionPublisher cung cấp số liệu giám sát nào?

`SubmissionPublisher<T>` là implementation của `Flow.Publisher<T>`, được bổ sung trong Java 9. Publisher gửi item bất đồng bộ đến các subscriber thông qua một `Executor`. Mỗi subscriber có buffer riêng, vì producer và các consumer có thể xử lý dữ liệu với tốc độ khác nhau.

Khi vận hành publisher, thường cần biết:

- Có bao nhiêu subscriber đang đăng ký?
- Có bao nhiêu item đã được gửi nhưng subscriber chậm nhất chưa tiêu thụ?
- Các subscriber còn bao nhiêu demand đã yêu cầu nhưng producer chưa đáp ứng?

Java 9 cung cấp hai phương thức ước lượng dành cho việc quan sát:

- `estimateMaximumLag()`: ước lượng số item lớn nhất đã được publish nhưng chưa được consume trong số các subscriber hiện tại.
- `estimateMinimumDemand()`: ước lượng demand nhỏ nhất đã được subscriber yêu cầu bằng `request(n)` nhưng producer chưa đáp ứng, xét trên các subscriber hiện tại.

Hai giá trị này bổ sung cho nhau: lag nhìn về phía dữ liệu đang chờ được tiêu thụ; demand nhìn về phía số lượng item mà subscriber vẫn cho phép publisher gửi tiếp.

## 2. estimateMaximumLag: quan sát lượng dữ liệu đang chờ

Chữ ký:

```java
public int estimateMaximumLag()
```

Phương thức trả về ước lượng số item lớn nhất đã được tạo/gửi nhưng chưa được tiêu thụ trong tất cả subscriber hiện tại.

Ví dụ, nếu có ba subscriber và backlog ước lượng lần lượt là 2, 0 và 7 item, maximum lag phản ánh mức lớn nhất là khoảng 7 item, không phải tổng backlog 9 item.

Cách đọc số liệu:

- Giá trị thấp và ổn định thường cho thấy consumer theo kịp producer.
- Giá trị tăng liên tục có thể báo hiệu một hoặc nhiều consumer xử lý chậm, executor thiếu năng lực hoặc tốc độ producer vượt tốc độ tiêu thụ.
- Giá trị cao nhưng giảm dần có thể cho thấy consumer đang xử lý phần backlog đã tích lũy.
- Giá trị 0 không chứng minh toàn bộ hệ thống không có độ trễ; nó chỉ là snapshot ước lượng backlog theo định nghĩa của API tại thời điểm đọc.

`estimateMaximumLag()` đo số lượng item, không đo thời gian. Một backlog 20 item có thể được xử lý trong vài millisecond hoặc vài giây, tùy kích thước công việc và tốc độ consumer. Vì vậy không được gọi giá trị này là latency tính bằng thời gian.

## 3. estimateMinimumDemand: quan sát nhu cầu còn lại

Chữ ký:

```java
public long estimateMinimumDemand()
```

Phương thức trả về ước lượng số item nhỏ nhất mà các subscriber đã yêu cầu bằng `Flow.Subscription.request(n)` nhưng publisher chưa gửi để đáp ứng demand đó.

Đây là giá trị nhỏ nhất trên các subscriber, không phải tổng demand của tất cả subscriber:

- Nếu subscriber A còn demand 8 và subscriber B còn demand 3, minimum demand phản ánh khoảng 3.
- Nếu một subscriber không có demand còn lại, minimum demand có thể bằng 0 dù subscriber khác vẫn còn demand.
- Nếu không có subscriber, phương thức trả về 0.

Ví dụ với một subscriber:

```java
subscription.request(5);
long demand = publisher.estimateMinimumDemand();
```

Ngay sau khi yêu cầu được ghi nhận và trước khi producer gửi item, ước lượng demand có thể là 5. Khi producer gửi item để đáp ứng một phần demand, giá trị có thể giảm. Vì đây là ước lượng concurrent, không nên yêu cầu một snapshot phải bằng chính xác số phép tính mà ứng dụng vừa thực hiện.

Minimum demand hữu ích để phát hiện subscriber không yêu cầu thêm dữ liệu hoặc demand còn lại đang thấp. Nó không phải tốc độ xử lý, không phải số slot buffer còn trống và cũng không phải số item đã được xử lý thành công.

## 4. Phân biệt lag, demand, buffer và latency

| Số liệu | Ý nghĩa | Đơn vị |
|---|---|---|
| `estimateMaximumLag()` | Backlog lớn nhất ước lượng trong các subscriber | Item |
| `estimateMinimumDemand()` | Demand nhỏ nhất còn chưa được đáp ứng | Item |
| `getNumberOfSubscribers()` | Số subscriber hiện tại | Subscriber |
| `getMaxBufferCapacity()` | Sức chứa tối đa của buffer mỗi subscriber | Item |
| Queue wait time tự đo | Thời gian từ lúc publish đến lúc subscriber nhận item | Thời gian |
| Processing time tự đo | Thời gian subscriber xử lý một item | Thời gian |

Mỗi subscriber có buffer riêng. Do đó một subscriber chậm có thể làm tăng maximum lag và gây áp lực lên thao tác publish, dù các subscriber còn lại vẫn xử lý nhanh.

Không nên suy luận latency chỉ từ buffer capacity hoặc demand. Buffer là giới hạn lưu trữ; demand là số item subscriber cho phép nhận; lag là lượng dữ liệu chưa được tiêu thụ. Ba khái niệm này liên quan nhưng không thay thế nhau.

## 5. Các phương thức giám sát subscriber khác

Ngoài hai số liệu ước lượng, `SubmissionPublisher` có các phương thức hữu ích:

- `hasSubscribers()`: kiểm tra publisher hiện có subscriber hay không.
- `getNumberOfSubscribers()`: lấy số subscriber hiện tại.
- `getSubscribers()`: lấy danh sách subscriber hiện tại để monitoring và tracking.
- `isSubscribed(subscriber)`: kiểm tra một subscriber cụ thể còn đăng ký hay không.
- `getMaxBufferCapacity()`: lấy sức chứa tối đa của buffer mỗi subscriber.
- `isClosed()` và `getClosedException()`: quan sát trạng thái đóng của publisher.

Danh sách từ `getSubscribers()` chỉ dành cho việc giám sát và tracking. Không gọi các phương thức của `Flow.Subscriber` trên các phần tử lấy từ danh sách đó. Việc yêu cầu demand hoặc hủy subscription phải được thực hiện qua `Flow.Subscription` mà subscriber nhận trong `onSubscribe`.

Các phương thức trên cung cấp ảnh chụp trạng thái tại thời điểm gọi. Subscriber có thể đăng ký hoặc hủy trong khi chương trình đang quan sát, nên cần xử lý việc số lượng thay đổi giữa hai lần đọc.

## 6. Lag không phải latency: tự đo thời gian giao nhận

`SubmissionPublisher` không cung cấp một phương thức trả về độ trễ theo millisecond hoặc nanosecond. Nếu cần đo thời gian từ publish đến khi subscriber nhận item, hãy gắn timestamp vào dữ liệu.

Dùng `System.nanoTime()` để đo khoảng thời gian trong cùng JVM:

```java
final class TimedItem<T> {
    final T value;
    final long publishedAtNanos;

    TimedItem(T value, long publishedAtNanos) {
        this.value = value;
        this.publishedAtNanos = publishedAtNanos;
    }
}

// Phía producer:
publisher.submit(new TimedItem<>(value, System.nanoTime()));

// Trong Flow.Subscriber.onNext:
long queueDelayNanos =
        System.nanoTime() - item.publishedAtNanos;
```

Có thể đo thêm thời gian xử lý:

```java
long startedAt = System.nanoTime();
process(item.value);
long processingNanos = System.nanoTime() - startedAt;
```

Hai số liệu có ý nghĩa khác nhau:

- Queue delay: thời gian từ lúc producer đóng dấu item đến lúc subscriber bắt đầu nhận/xử lý item.
- Processing time: thời gian subscriber thực hiện logic xử lý item.

Nếu cần đánh giá chất lượng dịch vụ, hãy thu thập histogram hoặc phân vị p50/p95/p99, thay vì chỉ nhìn giá trị trung bình. Với item đi qua nhiều stage, có thể gắn timestamp tại từng stage để tách thời gian chờ và thời gian xử lý.

`System.nanoTime()` dùng để đo thời lượng, không phải đồng hồ lịch. Không lưu nó làm timestamp tuyệt đối để so sánh giữa các máy hoặc sau khi JVM khởi động lại.

## 7. Dùng số liệu để phát hiện tình trạng producer-consumer mất cân bằng

Có thể kết hợp hai ước lượng để đọc tình trạng hệ thống:

| Maximum lag | Minimum demand | Cách diễn giải có thể xảy ra |
|---|---|---|
| Thấp | Cao | Subscriber còn demand và backlog nhỏ; publisher có thể đang gửi nhanh hơn nhịp consume nhưng chưa tích lũy nhiều |
| Cao, tăng liên tục | Thấp hoặc 0 | Ít nhất một subscriber có thể đang chậm hoặc không yêu cầu thêm item |
| Cao | Cao | Vẫn còn demand nhưng producer đã tạo nhiều item chưa được tiêu thụ; kiểm tra tốc độ xử lý và kích thước công việc |
| Thấp | Thấp hoặc 0 | Có thể subscriber đang xử lý hết dữ liệu đã yêu cầu và chưa yêu cầu thêm; không nhất thiết là lỗi |
| Dao động mạnh | Dao động mạnh | Tải hoặc lịch thực thi không ổn định; cần quan sát theo cửa sổ thời gian |

Đây là các dấu hiệu để điều tra, không phải kết luận chắc chắn. Nên lấy mẫu theo chu kỳ phù hợp, lưu cùng timestamp và đối chiếu với tốc độ publish, số item xử lý, thời gian xử lý và số lần drop.

Một snapshot duy nhất thường không đủ để kết luận consumer đang chậm. Xu hướng theo thời gian có giá trị hơn: lag tăng trong nhiều chu kỳ liên tiếp đáng quan tâm hơn một lần lag cao thoáng qua.

## 8. Liên hệ với submit, offer và backpressure

`SubmissionPublisher` hỗ trợ hai chính sách publish chính:

### submit(item)

`submit(item)` gửi item đến subscriber hiện tại và có thể block không ngắt được khi buffer của subscriber chưa có tài nguyên. Phương thức trả về ước lượng maximum lag sau lần publish. Nếu có subscriber, kết quả tính cả item vừa submit và ít nhất là 1; nếu không có subscriber, kết quả là 0.

```java
int lag = publisher.submit(item);
```

### offer(item, onDrop)

`offer` cố gắng publish mà không chờ vô hạn khi buffer bị bão hòa. Nếu không thể gửi cho một số subscriber, drop handler được gọi; handler có thể yêu cầu thử lại một lần.

Giá trị trả về có ý nghĩa:

- Số âm: số lần gửi bị drop được biểu diễn bằng số âm.
- Không âm: ước lượng maximum lag.

Overload có timeout cho phép chờ tài nguyên trong khoảng thời gian giới hạn trước khi gọi drop handler. Cần chọn chính sách dựa trên yêu cầu dữ liệu:

- Dữ liệu không được phép mất: cân nhắc `submit` và chấp nhận backpressure/blocking.
- Dữ liệu có thể bỏ qua hoặc thay thế: cân nhắc `offer` với drop handler và ghi nhận số lần drop.
- Cần giới hạn thời gian chờ: dùng overload `offer` có timeout và định nghĩa rõ hành vi khi hết thời gian.

Không dùng `estimateMaximumLag()` để tự triển khai một phép kiểm tra kiểu “nếu lag thấp thì submit, nếu lag cao thì dừng”. Kết quả ước lượng có thể cũ ngay sau khi đọc; producer khác hoặc subscriber khác có thể thay đổi trạng thái trước khi hành động xảy ra. Dùng trực tiếp chính sách `submit`/`offer` và demand của Flow để điều khiển luồng dữ liệu.

## 9. Ví dụ Java chạy được: quan sát demand và lag có kiểm soát

Ví dụ dùng một subscriber cố ý tạm dừng trong `onNext`. Producer chỉ gửi một item, nhờ đó có thể quan sát backlog khi callback chưa hoàn tất. Các latch làm cho thời điểm đọc số liệu có thể kiểm soát được, không phụ thuộc vào việc consumer xử lý quá nhanh.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class SubmissionPublisherMetricsDemo {
    private static final class PausingSubscriber
            implements Flow.Subscriber<Integer> {
        private final CountDownLatch subscribed = new CountDownLatch(1);
        private final CountDownLatch itemReceived = new CountDownLatch(1);
        private final CountDownLatch releaseItem = new CountDownLatch(1);
        private final CountDownLatch completed = new CountDownLatch(1);
        private volatile Flow.Subscription subscription;

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            subscribed.countDown();
        }

        @Override
        public void onNext(Integer item) {
            itemReceived.countDown();
            try {
                if (!releaseItem.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                            "test did not release subscriber");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(ex);
            }
        }

        @Override
        public void onError(Throwable error) {
            completed.countDown();
        }

        @Override
        public void onComplete() {
            completed.countDown();
        }

        void awaitSubscribed() throws InterruptedException {
            if (!subscribed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("subscriber was not subscribed");
            }
        }

        void request(long count) {
            subscription.request(count);
        }

        void awaitItemReceived() throws InterruptedException {
            if (!itemReceived.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("item was not delivered");
            }
        }

        void releaseItem() {
            releaseItem.countDown();
        }

        void awaitCompleted() throws InterruptedException {
            if (!completed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("publisher did not complete");
            }
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        SubmissionPublisher<Integer> publisher =
                new SubmissionPublisher<>(executor, 8);
        PausingSubscriber subscriber = new PausingSubscriber();

        try {
            publisher.subscribe(subscriber);
            subscriber.awaitSubscribed();
            System.out.println("subscriber count = "
                    + publisher.getNumberOfSubscribers());
            System.out.println("minimum demand before request = "
                    + publisher.estimateMinimumDemand());

            subscriber.request(3);
            System.out.println("minimum demand after request = "
                    + publisher.estimateMinimumDemand());

            int submitLag = publisher.submit(42);
            subscriber.awaitItemReceived();
            System.out.println("submit lag estimate = " + submitLag);
            System.out.println("maximum lag while onNext is blocked = "
                    + publisher.estimateMaximumLag());
            System.out.println("minimum demand while onNext is blocked = "
                    + publisher.estimateMinimumDemand());

            subscriber.releaseItem();
            publisher.close();
            subscriber.awaitCompleted();
        } finally {
            subscriber.releaseItem();
            publisher.close();
            executor.shutdownNow();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("executor did not terminate");
            }
        }
    }
}
```

Lưu mã nguồn trong `SubmissionPublisherMetricsDemo.java`, biên dịch và chạy bằng Java 9 trở lên:

```bash
javac --release 9 -Xlint:all SubmissionPublisherMetricsDemo.java
java SubmissionPublisherMetricsDemo
```

Kết quả:

```text
subscriber count = 1
minimum demand before request = 0
minimum demand after request = 3
submit lag estimate = 1
maximum lag while onNext is blocked = 1
minimum demand while onNext is blocked = 2
```

Subscriber bắt đầu với demand bằng 0. Sau khi yêu cầu 3 item, minimum demand được ước lượng là 3. Producer gửi một item và subscriber bắt đầu `onNext`, nhưng callback đang bị giữ lại bởi latch. Tại thời điểm đó, một item chưa được consume nên maximum lag là 1; demand còn lại được ước lượng là 2.

Ví dụ chủ động giữ callback để quan sát trạng thái. Trong ứng dụng thật, không block `onNext` bằng latch; hãy giữ callback ngắn, xử lý dữ liệu phù hợp hoặc chuyển công việc sang executor riêng có giới hạn.

## 10. Những giới hạn cần nhớ khi đọc số liệu

- **Chỉ là ước lượng:** lag và demand có thể phản ánh trạng thái cũ hoặc không chính xác tuyệt đối do publisher và subscriber hoạt động đồng thời.
- **Chỉ dành cho monitoring:** không dùng chúng làm khóa, điều kiện đồng bộ, hay bảo đảm rằng lần publish tiếp theo chắc chắn thành công.
- **Là số liệu tổng hợp:** maximum lag là mức lớn nhất giữa các subscriber; minimum demand là mức nhỏ nhất giữa các subscriber. Chúng không cho biết đầy đủ trạng thái riêng của từng subscriber.
- **Không phải thời gian:** lag tính theo item; muốn đo latency cần timestamp hoặc metric riêng.
- **Buffer độc lập:** mỗi subscriber có buffer riêng; một subscriber chậm có thể tạo áp lực dù subscriber khác vẫn theo kịp.
- **Executor ảnh hưởng delivery:** thread pool quá nhỏ, bị nghẽn hoặc từ chối task có thể làm subscriber nhận item chậm hoặc khiến quá trình notify thất bại.
- **Không gọi phương thức subscriber từ getSubscribers():** danh sách trả về chỉ dành cho monitoring/tracking; demand và cancellation đi qua subscription.

## 11. Checklist khi vận hành

1. Đã theo dõi số subscriber và trạng thái publisher đóng/mở chưa?
2. Maximum lag có tăng liên tục qua nhiều lần lấy mẫu không?
3. Minimum demand có thường xuyên về 0 ở một publisher có subscriber không?
4. Có đo queue delay và processing time riêng bằng timestamp không?
5. Đã phân biệt backlog với buffer capacity và demand chưa?
6. Chính sách publish là block bằng `submit` hay drop có kiểm soát bằng `offer`?
7. Có ghi nhận số item bị drop và lỗi từ executor/subscriber không?
8. Có tránh dùng số liệu ước lượng để quyết định đồng bộ hoặc đảm bảo correctness không?

`estimateMaximumLag()` và `estimateMinimumDemand()` là các chỉ số quan sát hữu ích cho luồng reactive. Hãy dùng xu hướng của chúng để phát hiện mất cân bằng producer-consumer, rồi kết hợp timestamp và metric của từng subscriber để đo latency thực tế và quyết định cách xử lý backpressure.

## 12. Tài liệu tham khảo

- [SubmissionPublisher — Java SE 9 API](https://cr.openjdk.org/~jjg/java-javafx-jdk-docs.OLD/api/java/util/concurrent/SubmissionPublisher.html)
- [SubmissionPublisher — Java SE API hiện hành](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html)
- [Flow — Java SE API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Flow.html)