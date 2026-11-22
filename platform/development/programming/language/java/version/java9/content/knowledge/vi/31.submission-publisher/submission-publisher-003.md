# submit, thời điểm chặn và ảnh hưởng của bên nhận chậm

`SubmissionPublisher<T>` là implementation của `Flow.Publisher<T>` được bổ sung trong Java 9. Nó nhận phần tử từ producer, lưu tạm dữ liệu trong buffer riêng của từng subscriber và phát `onNext` bất đồng bộ qua một Executor.

Phương thức `submit(item)` có chính sách giữ dữ liệu: nó chờ cho tới khi có đủ tài nguyên buffer để gửi phần tử tới các subscriber hiện tại. Vì vậy, khi một subscriber tiêu thụ chậm và buffer của subscriber đó đầy, luồng gọi `submit` có thể bị chặn. Một subscriber chậm có thể làm giảm tốc độ của producer dù các subscriber khác vẫn đang xử lý tốt.

Bài này tập trung vào thời điểm `submit` chặn, cách buffer và demand tương tác, ảnh hưởng của subscriber chậm, cách dùng `offer` khi cần giới hạn thời gian chờ hoặc chấp nhận bỏ dữ liệu, và cách kiểm thử hành vi đó.

## 1. SubmissionPublisher phát dữ liệu như thế nào?

Một `SubmissionPublisher<T>` phối hợp ba thành phần:

- **Producer:** gọi `submit(item)` hoặc `offer(item, ...)` để gửi dữ liệu.
- **SubmissionPublisher:** quản lý danh sách subscriber, buffer riêng cho từng subscriber và Executor dùng để giao dữ liệu.
- **Subscriber:** nhận `onNext(item)` theo demand đã cấp qua `Flow.Subscription.request(n)`.

Luồng xử lý khái quát:

~~~text
Producer
   |
   | submit(item)
   v
SubmissionPublisher
   |
   +---- buffer của Subscriber A ----> Executor ----> onNext(item)
   |
   +---- buffer của Subscriber B ----> Executor ----> onNext(item)
   |
   +---- buffer của Subscriber C ----> Executor ----> onNext(item)
~~~

Việc gọi `submit` không đồng nghĩa callback `onNext` được chạy ngay trên thread của producer. SubmissionPublisher giao callback bất đồng bộ qua Executor đã cấu hình.

Mỗi subscriber có buffer độc lập. Buffer hấp thụ chênh lệch tạm thời giữa tốc độ gửi và tốc độ nhận. Demand quyết định số phần tử publisher được phép giao; buffer lưu các phần tử đang chờ được giao hoặc tiêu thụ.

## 2. submit(item) chặn trong trường hợp nào?

Chữ ký:

~~~java
int submit(T item);
~~~

`submit` gửi phần tử tới từng subscriber hiện tại. Nếu buffer của một subscription không còn tài nguyên để tiếp nhận phần tử, phương thức sẽ chờ cho tới khi có chỗ. API mô tả đây là hành vi chờ *uninterruptibly*; phương thức không có tham số timeout hoặc chính sách drop.

Có thể chia thành ba trường hợp:

1. **Các buffer còn chỗ:** phần tử được xếp vào buffer tương ứng, callback được lên lịch bất đồng bộ và `submit` thường trả về nhanh.
2. **Một buffer đã đầy:** `submit` phải chờ tài nguyên cho subscription đó. Producer bị chặn cho tới khi subscriber tiêu thụ dữ liệu, hủy subscription hoặc một điều kiện khác làm tài nguyên khả dụng.
3. **Không có subscriber hiện tại:** không có buffer subscriber nào cần nhận phần tử; `submit` trả về 0 và phần tử không được lưu để phát lại cho subscriber đăng ký sau.

Chỉ cần tài nguyên của bất kỳ subscription hiện tại nào không sẵn sàng, lời gọi gửi có thể phải chờ. Nếu một subscriber vẫn đăng ký nhưng không request hoặc không tiêu thụ phần tử, buffer của nó có thể đầy và khiến producer chờ vô thời hạn. `submit` không tự loại subscriber chậm và cũng không tự bỏ phần tử để tiếp tục.

## 3. Vì sao subscriber chậm ảnh hưởng producer?

Giả sử publisher có hai subscriber:

- Subscriber A xử lý nhanh và thường xuyên request thêm.
- Subscriber B xử lý chậm, hoặc tạm thời không request thêm.

Mỗi subscriber có buffer riêng. Ban đầu, producer vẫn có thể gửi dữ liệu vào cả hai buffer. Subscriber A có thể nhận và xử lý các phần tử của mình trong khi B còn đang giữ dữ liệu chờ.

Khi buffer của B đầy, lời gọi `submit` tiếp theo cần chỗ trống cho B. Producer sẽ chặn tại lời gọi đó, nên nó không thể tiếp tục gửi các phần tử mới cho A qua các lần submit tiếp theo. Đây là cách subscriber chậm tạo ra áp lực ngược lên nguồn phát.

~~~text
Producer ---- submit(1) ----> A: buffer / xử lý nhanh
                   \--------> B: buffer / xử lý chậm

Producer ---- submit(2) ----> A: tiếp tục nhận
                   \--------> B: buffer đầy

Producer ---- submit(3) ----> CHỜ B có chỗ trống
                              |
                              +-- A có thể đã xử lý xong
                                  nhưng producer vẫn chờ
~~~

Subscriber chậm không nhất thiết làm callback của subscriber nhanh chạy chậm trực tiếp. Ảnh hưởng chính là nó có thể làm producer bị chặn, khiến toàn bộ nguồn phát giảm tốc độ và subscriber nhanh không còn nhận được những phần tử mới mà producer chưa thể gửi.

Nếu producer có nhiều thread gửi đồng thời, một số thread có thể cùng bị chặn ở các lời gọi submit. Điều này làm giảm số thread sẵn sàng xử lý công việc khác và có thể tạo hiệu ứng dây chuyền trong ứng dụng.

## 4. Buffer, demand và tốc độ tiêu thụ

Buffer và demand giải quyết hai vấn đề liên quan nhưng khác nhau:

- **Demand:** subscriber cho biết mình sẵn sàng nhận thêm bao nhiêu phần tử bằng `request(n)`.
- **Buffer:** nơi SubmissionPublisher lưu tạm phần tử đang chờ được giao cho subscriber.

Ví dụ subscriber chỉ request một phần tử:

~~~java
@Override
public void onSubscribe(Flow.Subscription subscription) {
    this.subscription = subscription;
    subscription.request(1);
}
~~~

Sau khi nhận một phần tử, nếu subscriber không request thêm, publisher không thể tiếp tục giao các phần tử tiếp theo cho subscriber đó. Các phần tử producer gửi sau có thể nằm trong buffer cho tới khi subscriber request thêm.

Nếu producer tiếp tục gửi nhanh hơn subscriber tiêu thụ, buffer tăng dần. Khi buffer đạt giới hạn, `submit` sẽ chờ tài nguyên. Vì vậy, tăng buffer chỉ giúp hấp thụ burst ngắn; nó không giải quyết chênh lệch tốc độ kéo dài. Nếu tốc độ trung bình của producer luôn cao hơn khả năng tiêu thụ, buffer cuối cùng vẫn đầy.

### Chọn sức chứa buffer

Có thể cấu hình Executor và sức chứa tối đa mỗi subscriber:

~~~java
ExecutorService deliveryExecutor = Executors.newFixedThreadPool(2);

SubmissionPublisher<Event> publisher =
    new SubmissionPublisher<>(deliveryExecutor, 256);
~~~

Tham số sức chứa là giới hạn tối đa cho buffer của từng subscriber. Dung lượng được triển khai có thể được làm tròn lên lũy thừa hai hoặc giới hạn theo khả năng của implementation. `getMaxBufferCapacity()` trả về sức chứa thực tế được áp dụng.

Khi chọn capacity, cân nhắc:

- Tốc độ producer và tốc độ tiêu thụ thực tế.
- Kích thước trung bình của một phần tử.
- Độ dài burst mà ứng dụng cần hấp thụ.
- Số subscriber hiện tại và số subscriber dự kiến.
- Bộ nhớ có thể dành cho tất cả buffer.
- Hành vi mong muốn khi buffer đầy: chờ, drop có kiểm soát hoặc áp dụng giới hạn từ tầng producer.

Tăng capacity có thể giảm số lần producer phải chờ trong burst, nhưng đổi lại là tăng bộ nhớ có thể sử dụng và làm dữ liệu chờ lâu hơn.

## 5. submit trả về giá trị gì?

`submit(item)` trả về một số nguyên biểu diễn ước lượng lag lớn nhất trong các subscriber hiện tại sau khi gửi phần tử:

~~~java
int estimatedLag = publisher.submit(event);
System.out.println("estimated lag=" + estimatedLag);
~~~

Lag là số phần tử đã gửi nhưng subscriber chưa tiêu thụ. Giá trị trả về:

- Ít nhất là 1 nếu có subscriber, vì tính cả phần tử vừa gửi.
- Bằng 0 nếu không có subscriber.
- Là số ước lượng, có thể thay đổi ngay khi subscriber tiếp tục nhận dữ liệu.

Không được hiểu giá trị trả về là số subscriber bị chặn, thời gian chặn hoặc số phần tử đã drop. `submit` không drop phần tử theo chính sách bình thường; nếu tài nguyên không sẵn sàng, nó chờ.

Có thể quan sát thêm:

~~~java
int lag = publisher.estimateMaximumLag();
long demand = publisher.estimateMinimumDemand();
~~~

Hai phương thức trên cũng trả về ước lượng để monitoring. Chúng có thể đã cũ ngay sau khi đọc và không phải công cụ đồng bộ. Không dùng chúng để quyết định rằng một lời gọi submit tiếp theo chắc chắn sẽ không block.

## 6. Khi nào dùng offer thay cho submit?

Nếu producer không thể chờ vô hạn, SubmissionPublisher cung cấp các overload `offer`. Chúng cho phép áp dụng chính sách khi buffer của subscriber không nhận thêm được phần tử.

### offer không chờ

~~~java
int result = publisher.offer(event, (subscriber, droppedItem) -> {
    System.err.println("Dropped event: " + droppedItem);
    return false;
});
~~~

Overload này thử gửi phần tử tới các subscriber. Nếu một subscriber không có tài nguyên, phần tử có thể bị drop cho subscriber đó. Handler `onDrop`, nếu được cung cấp, nhận subscriber và phần tử bị drop:

- Trả về `true`: yêu cầu thử gửi lại một lần.
- Trả về `false`: chấp nhận drop cho subscriber đó.

Giá trị trả về có hai dạng:

- Không âm: ước lượng lag lớn nhất.
- Âm: số âm biểu thị số lần gửi thất bại/drop.

Một phần tử có thể được nhận bởi subscriber này nhưng bị drop ở subscriber khác. Vì vậy, các subscriber có thể quan sát những chuỗi phần tử khác nhau khi chính sách drop được sử dụng.

### offer có thời gian chờ hữu hạn

~~~java
int result = publisher.offer(
    event,
    100,
    TimeUnit.MILLISECONDS,
    (subscriber, droppedItem) -> {
        logDrop(subscriber, droppedItem);
        return false;
    }
);
~~~

Overload này chờ tài nguyên tối đa theo timeout đã chỉ định. Khi hết thời gian hoặc thread gửi bị interrupt, handler được gọi nếu có; nếu handler trả true, publisher thử gửi lại một lần.

Đây là lựa chọn khi ứng dụng muốn chờ trong khoảng hữu hạn rồi áp dụng chính sách drop. Giá trị âm cho biết có lần gửi bị drop; giá trị không âm là ước lượng lag lớn nhất.

Handler được gọi trong lúc các lời gọi method khác của SubmissionPublisher từ thread khác bị chặn. Vì vậy, handler nên ngắn gọn, tránh blocking lâu và tránh thực hiện các thao tác phụ thuộc vào publisher.

### Chọn chính sách

| Nhu cầu | API phù hợp |
|---|---|
| Không muốn mất phần tử; producer có thể chờ | `submit(item)` |
| Không muốn producer chờ; dữ liệu có thể drop | `offer(item, onDrop)` |
| Chỉ chờ tối đa một khoảng rồi xử lý drop | `offer(item, timeout, unit, onDrop)` |
| Dữ liệu bắt buộc đầy đủ như lệnh hoặc sự kiện tài chính | Chọn submit hoặc cơ chế lưu bền vững; không drop tùy tiện |
| Dữ liệu cập nhật mới thay thế dữ liệu cũ như trạng thái hiển thị | Có thể cân nhắc offer với chính sách drop phù hợp |

Không nên chọn offer chỉ để tránh thấy producer bị block nếu việc mất dữ liệu sẽ làm sai trạng thái nghiệp vụ. Cần xác định rõ phần tử nào có thể bỏ, ai chịu trách nhiệm xử lý drop và có cần lưu lại để thử gửi sau hay không.

## 7. Tránh chặn nhầm thread quan trọng

Vì `submit` có thể block, không nên gọi nó tùy tiện trên:

- Thread xử lý request HTTP cần trả phản hồi nhanh.
- Event loop hoặc UI thread.
- Thread điều phối tác vụ của ứng dụng.
- Thread duy nhất trong Executor đang chịu trách nhiệm gọi callback `onNext` để giải phóng buffer.

Trường hợp cuối đặc biệt dễ gây deadlock: nếu callback của subscriber gọi submit, rồi submit phải chờ buffer được giải phóng bởi callback khác đang chờ cùng một single-thread Executor, executor không còn thread để chạy callback giải phóng buffer.

Một cách tổ chức an toàn hơn là tách producer và executor giao callback:

~~~java
ExecutorService deliveryExecutor = Executors.newFixedThreadPool(2);
ExecutorService producerExecutor = Executors.newSingleThreadExecutor();

SubmissionPublisher<Event> publisher =
    new SubmissionPublisher<>(deliveryExecutor, 128);

producerExecutor.submit(() -> publisher.submit(nextEvent));
~~~

Producer có thể bị block trên executor riêng, còn delivery executor tiếp tục chạy callback subscriber. Cần đóng publisher và shutdown các executor theo vòng đời ứng dụng.

Không có một kích thước thread pool phù hợp cho mọi trường hợp. Chọn executor theo số subscriber, độ nặng của callback, số nguồn gửi và mức độ blocking dự kiến.

## 8. Theo dõi subscriber chậm

SubmissionPublisher có một số API monitoring:

| API | Ý nghĩa |
|---|---|
| `getNumberOfSubscribers()` | Số subscriber hiện tại |
| `getSubscribers()` | Danh sách subscriber để quan sát |
| `isSubscribed(subscriber)` | Kiểm tra subscriber có đang đăng ký |
| `estimateMaximumLag()` | Ước lượng lag lớn nhất |
| `estimateMinimumDemand()` | Ước lượng demand nhỏ nhất |
| `getMaxBufferCapacity()` | Sức chứa tối đa mỗi subscriber |
| `hasSubscribers()` | Có subscriber hiện tại hay không |

Có thể ghi nhận lag theo thời gian để tìm subscriber tiêu thụ chậm. Tuy nhiên, API không cung cấp một số đo chính xác tuyệt đối cho từng subscriber qua `estimateMaximumLag()`; đây là số liệu ước lượng tổng hợp.

Nếu cần chẩn đoán subscriber cụ thể, ứng dụng có thể tự đo thời gian xử lý trong `onNext`, số phần tử nhận, số lần request và trạng thái subscription. Không gọi trực tiếp phương thức callback trên các subscriber lấy từ `getSubscribers()`; danh sách đó dành cho monitoring.

Một subscriber chậm có thể được xử lý bằng các cách:

1. Tối ưu callback `onNext` hoặc chuyển phần việc nặng sang executor phù hợp.
2. Điều chỉnh batch request để subscriber có đủ demand khi xử lý.
3. Tăng buffer nếu vấn đề chỉ là burst ngắn và bộ nhớ cho phép.
4. Tách luồng dữ liệu hoặc publisher để subscriber chậm không chặn producer của luồng quan trọng khác.
5. Dùng offer nếu nghiệp vụ cho phép drop và đã có chính sách xử lý rõ ràng.
6. Hủy subscriber nếu subscriber không còn cần dữ liệu.

Tăng buffer không chữa được subscriber chậm vĩnh viễn. Cần sửa tốc độ tiêu thụ, tách tải hoặc chọn chính sách dữ liệu phù hợp.

## 9. Đóng publisher và xử lý lỗi

`close()` ngừng nhận phần tử mới và phát tín hiệu `onComplete()` tới các subscriber hiện tại. Việc giao tín hiệu là bất đồng bộ: khi `close()` trả về, không có bảo đảm rằng mọi subscriber đã hoàn tất callback `onComplete()`. Nếu cần biết subscriber đã kết thúc, hãy chờ tín hiệu đó bằng latch hoặc một cơ chế hoàn tất riêng.

`closeExceptionally(error)` kết thúc luồng bằng tín hiệu `onError(error)`.

~~~java
publisher.submit(finalEvent);
publisher.close();
~~~

Sau khi đóng, các lần gọi `submit` hoặc `offer` mới sẽ ném `IllegalStateException`. Phần tử gửi vào không được là null; nếu null, API ném `NullPointerException`.

SubmissionPublisher sử dụng Executor để lên lịch callback. Nếu Executor từ chối tác vụ bằng `RejectedExecutionException` hoặc ném RuntimeException/Error khác khi gửi thông báo bất đồng bộ, ngoại lệ được truyền lại và không có bảo đảm mọi subscriber đều đã nhận phần tử đó.

Vì vậy, executor phải còn hoạt động trong suốt thời gian publisher phát dữ liệu. Khi shutdown ứng dụng, hãy đóng publisher, đợi subscriber báo hoàn tất, rồi mới shutdown executor giao callback.

## 10. Ví dụ Java chạy được: buffer đầy làm submit chặn

Ví dụ tạo một subscriber cố ý xử lý chậm. Subscriber chỉ request một phần tử ban đầu và giữ callback của phần tử đầu tiên bằng CountDownLatch. Buffer có capacity tối đa là 1:

1. Gửi phần tử 1; subscriber bắt đầu xử lý và tạm dừng trong callback.
2. Gửi phần tử 2; phần tử này chiếm chỗ duy nhất trong buffer.
3. Gửi phần tử 3 trên một producer thread khác. Lời gọi submit phải chờ vì buffer đang đầy.
4. Mở latch để subscriber tiếp tục. Khi subscriber request và tiêu thụ phần tử 2, buffer có chỗ và submit phần tử 3 hoàn tất.

~~~java
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.Future;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

public class SubmissionPublisherSubmitExample {
    private static final class SlowSubscriber
            implements Flow.Subscriber<Integer> {
        private final CountDownLatch firstStarted = new CountDownLatch(1);
        private final CountDownLatch releaseFirst = new CountDownLatch(1);
        private final CountDownLatch completed = new CountDownLatch(1);
        private final Queue<Integer> received = new ConcurrentLinkedQueue<>();
        private Flow.Subscription subscription;
        private Throwable error;

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            subscription.request(1);
        }

        @Override
        public void onNext(Integer item) {
            received.add(item);
            if (item == 1) {
                firstStarted.countDown();
                try {
                    releaseFirst.await();
                } catch (InterruptedException ex) {
                    Thread.currentThread().interrupt();
                    subscription.cancel();
                    return;
                }
            }
            subscription.request(1);
        }

        @Override
        public void onError(Throwable error) {
            this.error = error;
            completed.countDown();
        }

        @Override
        public void onComplete() {
            completed.countDown();
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService deliveryExecutor =
            Executors.newSingleThreadExecutor();
        ExecutorService producerExecutor =
            Executors.newSingleThreadExecutor();
        SlowSubscriber subscriber = new SlowSubscriber();
        SubmissionPublisher<Integer> publisher =
            new SubmissionPublisher<>(deliveryExecutor, 1);

        try {
            publisher.subscribe(subscriber);
            publisher.submit(1);

            if (!subscriber.firstStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("First item was not delivered");
            }

            publisher.submit(2);

            CountDownLatch thirdAttemptStarted = new CountDownLatch(1);
            Future<Integer> thirdSubmission = producerExecutor.submit(() -> {
                thirdAttemptStarted.countDown();
                return publisher.submit(3);
            });

            if (!thirdAttemptStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Producer did not start");
            }

            boolean blocked;
            try {
                thirdSubmission.get(200, TimeUnit.MILLISECONDS);
                blocked = false;
            } catch (TimeoutException expected) {
                blocked = true;
            }

            if (!blocked) {
                throw new IllegalStateException("Third submission did not block");
            }

            subscriber.releaseFirst.countDown();
            thirdSubmission.get(5, TimeUnit.SECONDS);
            publisher.close();

            if (!subscriber.completed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Subscriber did not complete");
            }
            if (subscriber.error != null) {
                throw new IllegalStateException("Subscriber failed",
                    subscriber.error);
            }

            System.out.println(
                "third submit blocked while buffer full=true");
            System.out.println("received=" + subscriber.received);
            System.out.println("publisher closed=" + publisher.isClosed());
        } finally {
            subscriber.releaseFirst.countDown();
            publisher.close();
            producerExecutor.shutdownNow();
            deliveryExecutor.shutdown();
            producerExecutor.awaitTermination(5, TimeUnit.SECONDS);
            deliveryExecutor.awaitTermination(5, TimeUnit.SECONDS);
        }
    }
}
~~~

Lưu trong tệp `SubmissionPublisherSubmitExample.java`, biên dịch và chạy với Java 9 trở lên:

~~~shell
javac --release 9 -Xlint:all SubmissionPublisherSubmitExample.java
java SubmissionPublisherSubmitExample
~~~

Kết quả stdout chính xác:

~~~text
third submit blocked while buffer full=true
received=[1, 2, 3]
publisher closed=true
~~~

Giải thích:

- Subscriber request một phần tử. Callback `onNext(1)` bắt đầu và chờ latch, nên callback delivery executor chưa thể xử lý phần tử tiếp theo.
- `submit(2)` đặt phần tử thứ hai vào buffer có sức chứa 1.
- Producer thread gọi `submit(3)`. Vì buffer của subscriber đang đầy, lời gọi không thể hoàn tất trong 200 ms và Future ném TimeoutException cho lần chờ của main thread. Bản thân lời gọi submit vẫn đang chờ ở producer thread.
- Main mở latch. Subscriber hoàn tất phần tử 1, request thêm, rồi nhận phần tử 2. Khi buffer có chỗ, producer gửi được phần tử 3.
- Publisher được đóng sau khi phần tử 3 đã được gửi. Subscriber nhận đủ ba phần tử rồi gọi onComplete.

Timeout 200 ms trong ví dụ chỉ dùng để quan sát rằng producer chưa hoàn tất; nó không hủy lời gọi `submit(3)`. Latch được mở để giải phóng subscriber và cho producer tiếp tục.

## 11. Những lỗi thường gặp

- **Cho rằng submit luôn không block vì callback chạy bất đồng bộ:** callback bất đồng bộ, nhưng producer vẫn có thể block khi buffer của subscriber đầy.
- **Cho rằng chỉ subscriber chậm bị ảnh hưởng:** subscriber chậm làm producer chờ; các lần gửi mới cho những subscriber khác cũng bị trì hoãn.
- **Tăng buffer để giải quyết chênh lệch tốc độ lâu dài:** buffer lớn chỉ trì hoãn thời điểm đầy nếu producer liên tục nhanh hơn consumer.
- **Gọi submit trên event loop hoặc request thread:** khi buffer đầy, thread quan trọng có thể bị giữ lại trong thời gian dài.
- **Dùng chung single-thread executor cho producer blocking và callback delivery:** producer có thể chiếm thread cần thiết để subscriber giải phóng buffer.
- **Coi giá trị submit trả về là số subscriber chậm:** đây là ước lượng lag lớn nhất, không phải danh sách hoặc số lượng subscriber.
- **Dùng estimateMaximumLag để quyết định chắc chắn submit không block:** các giá trị monitoring có thể cũ ngay khi đọc.
- **Dùng offer nhưng bỏ qua giá trị âm:** giá trị âm biểu thị số lần gửi thất bại/drop; ứng dụng phải xử lý dữ liệu bị bỏ.
- **Giả định mọi subscriber nhận cùng dữ liệu khi offer có drop:** phần tử có thể được nhận ở subscriber này nhưng bị drop ở subscriber khác.
- **Đóng Executor trước publisher:** callback có thể bị từ chối khi SubmissionPublisher vẫn cần giao dữ liệu.
- **Cho rằng close() trả về nghĩa là mọi subscriber đã hoàn tất:** close phát tín hiệu hoàn tất nhưng không chờ mọi callback kết thúc.
- **Quên đóng publisher:** subscriber có thể không nhận onComplete và tài nguyên liên quan không được giải phóng đúng vòng đời.

## 12. Tài liệu tham khảo chính thức

- [SubmissionPublisher — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html): hợp đồng submit, offer, buffer độc lập theo subscriber, lag/demand và vòng đời publisher.
- [Flow — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/Flow.html): Publisher, Subscriber, Subscription và quy tắc demand.
- [JEP 266: More Concurrency Updates](https://openjdk.org/jeps/266): giới thiệu Flow API và SubmissionPublisher trong Java 9.