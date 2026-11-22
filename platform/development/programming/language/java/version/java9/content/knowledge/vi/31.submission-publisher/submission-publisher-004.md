# offer, thời hạn chờ và chính sách bỏ phần tử trong SubmissionPublisher

## 1. Bối cảnh: vì sao cần offer?

SubmissionPublisher là triển khai Flow.Publisher có sẵn từ Java 9. Publisher nhận item từ producer, lưu item vào buffer riêng của từng Subscriber rồi gửi callback bất đồng bộ qua Executor.

Producer và Subscriber có thể chạy với tốc độ khác nhau. Nếu Subscriber xử lý chậm, buffer của Subscriber đó có thể đầy. SubmissionPublisher cung cấp ba cách gửi với chính sách khác nhau:

- submit(item): chờ cho đến khi có tài nguyên buffer. Đây là lựa chọn đơn giản khi không muốn bỏ item.
- offer(item, onDrop): thử gửi ngay; nếu buffer không nhận được item, gọi handler và có thể thử lại một lần.
- offer(item, timeout, unit, onDrop): chờ tài nguyên trong khoảng thời gian giới hạn; nếu hết thời gian hoặc thread gọi bị interrupt, gọi handler và có thể thử lại một lần.

offer giúp producer kiểm soát phản ứng khi buffer đầy. Nó đặc biệt hữu ích cho telemetry, trạng thái cập nhật thường xuyên, dữ liệu giám sát hoặc luồng mà ứng dụng có chính sách xử lý mất dữ liệu rõ ràng.

Điểm cần nhớ: offer điều khiển việc đưa item vào buffer của Subscriber. Nó không chờ Subscriber xử lý xong onNext và cũng không phải xác nhận nghiệp vụ rằng người nhận đã hoàn thành công việc.

## 2. Buffer riêng cho từng Subscriber

SubmissionPublisher duy trì buffer độc lập cho từng Subscriber. Một Subscriber chậm có thể làm buffer của chính nó đầy trong khi Subscriber khác vẫn tiếp tục nhận item.

Ví dụ:

- Subscriber A xử lý nhanh nên buffer còn chỗ.
- Subscriber B xử lý chậm và không request thêm dữ liệu nên buffer đầy.
- Producer gọi offer(item, onDrop).
- A có thể nhận item, còn B có thể bị drop nếu không còn chỗ và handler không yêu cầu retry thành công.

Vì vậy, một lần offer không nhất thiết có kết quả đồng nhất cho tất cả Subscriber. Nếu có một Subscriber bị drop, kết quả trả về là số âm dù những Subscriber khác đã nhận được item.

Không được hiểu kết quả âm là item chưa được gửi cho bất kỳ ai. Nếu nghiệp vụ cần tất cả Subscriber nhận cùng một sự kiện, phải thiết kế cơ chế xác nhận, lưu trữ và phát lại phù hợp; offer không cung cấp giao dịch broadcast all-or-nothing.

Dung lượng buffer là giới hạn tối đa cho từng Subscriber. Implementation có thể làm tròn dung lượng được yêu cầu lên lũy thừa của hai hoặc giới hạn theo dung lượng lớn nhất hỗ trợ. Hãy coi tham số buffer là giới hạn cấu hình, không dựa vào một con số nội bộ ngoài hợp đồng API.

## 3. offer(item, onDrop): thử gửi ngay và xử lý drop

Overload đơn giản:

~~~java
int status = publisher.offer(item, (subscriber, droppedItem) -> {
    recordDrop(subscriber, droppedItem);
    return false;
});
~~~

Phương thức cố gắng gửi item đến các Subscriber hiện tại. Nếu buffer của một Subscriber không thể nhận item do giới hạn tài nguyên, handler onDrop được gọi với hai đối số:

- subscriber: Subscriber không nhận được item ở lần thử đó.
- droppedItem: item đang được gửi nhưng chưa được chấp nhận vào buffer của Subscriber đó.

Handler trả về boolean:

- false: chấp nhận bỏ item đối với Subscriber này; không thử lại.
- true: yêu cầu SubmissionPublisher thử gửi lại item một lần cho Subscriber đó.

Overload này không chờ một khoảng thời gian để buffer có chỗ. Nó phù hợp khi producer cần phản hồi nhanh và ứng dụng chấp nhận bỏ item theo chính sách đã chọn.

Handler là một phần của quá trình gọi offer. Giữ handler ngắn gọn: ghi metric, log có giới hạn hoặc quyết định retry. Không thực hiện công việc chậm trong handler. Trong lúc handler đang chạy, các lời gọi phương thức khác trên cùng SubmissionPublisher từ thread khác bị chặn.

## 4. offer có timeout: chờ buffer trong thời gian giới hạn

Overload có thời hạn:

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

Phương thức chờ tài nguyên cho những Subscription chưa có chỗ trong buffer, tối đa bằng timeout và unit. Khi hết thời gian hoặc thread gọi bị interrupt, handler được gọi. Nếu handler trả về true, item được thử gửi lại một lần.

Tham số:

| Tham số | Ý nghĩa |
|---|---|
| item | Item không được null cần gửi |
| timeout | Thời gian chờ tối đa |
| unit | Đơn vị thời gian, ví dụ MILLISECONDS hoặc SECONDS |
| onDrop | Handler quyết định bỏ item hay yêu cầu retry một lần |

Timeout ở đây là thời gian producer chờ tài nguyên buffer. Nó không phải deadline xử lý của Subscriber. Một item có thể được nhận vào buffer trong thời hạn nhưng callback onNext chỉ chạy sau đó.

Timed offer vẫn có thể chặn thread gọi trong tối đa khoảng thời gian đã cấu hình. Không gọi nó trên UI thread hoặc event loop cần phản hồi nhanh nếu timeout có thể gây nghẽn.

Nếu timeout bằng 0, phương thức không dành thời gian chờ tài nguyên; handler vẫn có thể được gọi khi không thể gửi item.

## 5. Phân biệt timeout và interrupt trong drop handler

Timed offer cũng có thể dừng chờ khi thread gọi bị interrupt. Handler có thể phân biệt trường hợp interrupt với timeout bằng cách kiểm tra trạng thái interrupt của thread hiện tại:

~~~java
int status = publisher.offer(
    item,
    1,
    TimeUnit.SECONDS,
    (subscriber, droppedItem) -> {
        if (Thread.currentThread().isInterrupted()) {
            recordInterruptedOffer(subscriber, droppedItem);
            return false;
        }

        recordTimedOutOffer(subscriber, droppedItem);
        return false;
    }
);
~~~

Nếu thread bị interrupt, không nên mặc định retry. Hãy tuân theo chính sách hủy của tác vụ đang chạy, ghi nhận nguyên nhân và để tầng gọi quyết định có tiếp tục gửi hay không.

Handler không nhận riêng một enum nguyên nhân timeout/interrupt. Nếu cần phân biệt, dùng trạng thái interrupt của thread tại thời điểm handler chạy.

Không dùng timeout của offer như một cách thay thế cho interrupt hoặc cancellation. Timeout giới hạn việc chờ buffer; interrupt thể hiện yêu cầu dừng hoặc hủy công việc của thread gọi.

## 6. Handler trả về true chỉ retry một lần

Giá trị true không có nghĩa SubmissionPublisher sẽ thử mãi đến khi thành công. Nó chỉ yêu cầu một lần thử lại sau khi handler xử lý tình huống drop.

~~~java
int status = publisher.offer(
    item,
    100,
    TimeUnit.MILLISECONDS,
    (subscriber, droppedItem) -> {
        recordDrop(subscriber, droppedItem);

        if (Thread.currentThread().isInterrupted()) {
            return false;
        }

        return true;
    }
);
~~~

Nếu lần thử lại vẫn không có chỗ trong buffer, item vẫn có thể bị drop. Handler không được gọi lặp vô hạn cho cùng một lần offer.

Chỉ trả về true khi có lý do hợp lý để lần thử lại có khả năng thành công, chẳng hạn một điều kiện bên ngoài vừa được giải quyết. Đừng trả về true một cách máy móc cho mọi drop vì nó không biến buffer đầy thành buffer có dung lượng vô hạn.

Handler có thể được gọi cho nhiều Subscriber trong cùng một lần offer nếu nhiều buffer đều không nhận được item. Mỗi lần gọi cung cấp Subscriber và item tương ứng. Hãy tính metric theo từng lần drop thay vì giả định một item chỉ tạo tối đa một callback handler.

## 7. Ý nghĩa giá trị trả về

Cả hai overload offer trả về int với hai cách diễn giải:

- Giá trị âm: đối dấu của giá trị trả về là số lần không gửi được item tới Subscriber (số lần drop).
- Giá trị không âm: ước lượng độ trễ lớn nhất, tức số item đã gửi nhưng chưa được tiêu thụ, trong các Subscriber hiện tại.

Ví dụ:

~~~java
int status = publisher.offer(item, onDrop);

if (status < 0) {
    int droppedCount = -status;
    System.out.println("Dropped for subscribers: " + droppedCount);
} else {
    int estimatedMaxLag = status;
    System.out.println("Estimated maximum lag: " + estimatedMaxLag);
}
~~~

Nếu có Subscriber, giá trị lag không âm tối thiểu là 1 để tính item vừa gửi; nếu không có Subscriber thì có thể là 0.

Giá trị lag chỉ là ước lượng tại thời điểm quan sát, không phải số liệu đồng bộ chính xác để quyết định thứ tự hay khóa tài nguyên. Dùng nó cho monitoring, dashboard và điều chỉnh tải theo xu hướng; không dùng nó như xác nhận rằng mọi Subscriber đã xử lý xong item.

Một kết quả âm cũng không có nghĩa toàn bộ lần gửi thất bại. Một số Subscriber có thể nhận item trong khi những Subscriber khác bị drop.

## 8. So sánh submit và hai overload offer

| Phương thức | Khi buffer đầy | Có thể chờ? | Có drop handler? |
|---|---|---|---|
| submit(item) | Chờ tài nguyên buffer | Có, chặn không giới hạn và không hủy chờ bằng interrupt | Không |
| offer(item, onDrop) | Gọi handler ngay khi không thể gửi | Không chờ buffer có chỗ | Có |
| offer(item, timeout, unit, onDrop) | Chờ tối đa timeout, sau đó gọi handler | Có, nhưng có giới hạn | Có |

submit là lựa chọn dễ dùng khi không được phép mất item, nhưng nó chặn producer không thể hủy chờ bằng interrupt. Tránh gọi submit trên thread giao diện, event loop hoặc thread phục vụ nhiều request nếu buffer đầy có thể làm nghẽn hệ thống.

offer không timeout phù hợp khi cần phản hồi nhanh và có thể bỏ item. Timed offer là lựa chọn trung gian: chờ một khoảng ngắn để giảm drop, sau đó thực hiện chính sách bỏ hoặc retry.

Không có phương thức nào tự bảo đảm mọi Subscriber đã xử lý xong dữ liệu. submit chỉ chờ tài nguyên buffer để gửi item; nó không đợi callback onNext hoàn tất.

## 9. Chọn chính sách drop theo loại dữ liệu

Không có một chính sách drop đúng cho mọi ứng dụng. Quyết định phụ thuộc vào ý nghĩa của item.

### Telemetry và metric tần suất cao

Nếu một vài mẫu bị mất vẫn chấp nhận được, có thể dùng offer và đếm số lần drop. Giữ metric tổng hợp về số item gửi, số drop và lag để nhận biết Subscriber nào đang chậm.

Không log từng item bị drop ở tải lớn vì log có thể tạo thêm áp lực lên hệ thống. Nên dùng counter, sampling hoặc log tổng hợp theo chu kỳ.

### Trạng thái mới nhất

Với dữ liệu biểu diễn trạng thái hiện tại, item cũ có thể ít giá trị hơn item mới. Ứng dụng có thể lưu trạng thái mới nhất bên ngoài Publisher và phát lại khi có khả năng. Handler của offer chỉ quyết định retry một lần; nó không cung cấp API để xóa tùy ý item cũ khỏi buffer của Subscriber.

Nếu cần chính sách drop-oldest hoặc coalesce nhiều bản cập nhật thành một, hãy xây dựng lớp buffer/coalescing riêng trước Publisher hoặc dùng một cấu trúc phù hợp với nghiệp vụ.

### Sự kiện nghiệp vụ không được mất

Không nên âm thầm drop các sự kiện như thanh toán, thay đổi đơn hàng hoặc lệnh quan trọng. Hãy cân nhắc:

- Dùng submit nếu việc chờ producer là chấp nhận được.
- Lưu sự kiện vào hàng đợi bền vững trước khi phát.
- Retry ở tầng producer với giới hạn và backoff.
- Theo dõi xác nhận xử lý ở tầng nghiệp vụ nếu cần biết Subscriber đã hoàn thành.

offer không phải cơ chế lưu trữ bền vững và không thay thế xác nhận xử lý.

## 10. Handler cần ngắn và an toàn

Drop handler chạy trong quá trình offer. Trong thời gian handler được gọi, các lời gọi phương thức khác trên cùng SubmissionPublisher từ thread khác bị chặn. Vì vậy:

- Không gọi dịch vụ mạng hoặc database chậm.
- Không chờ vô thời hạn trong handler.
- Không gọi ngược các phương thức publish của cùng Publisher.
- Không giữ lock ứng dụng lâu hoặc chờ thread khác cần gọi Publisher.
- Không ném exception tùy tiện; exception từ handler sẽ được truyền ra khỏi offer.
- Không giả định handler chỉ chạy một lần cho toàn bộ item; nhiều Subscriber có thể bị drop độc lập.

Ví dụ handler gọn:

~~~java
AtomicLong droppedItems = new AtomicLong();

int status = publisher.offer(
    item,
    50,
    TimeUnit.MILLISECONDS,
    (subscriber, droppedItem) -> {
        droppedItems.incrementAndGet();
        return false;
    }
);
~~~

Nếu cần xử lý phức tạp, handler nên ghi nhận sự kiện vào một hàng đợi metric riêng có giới hạn và để worker khác xử lý sau.

## 11. Lỗi và giới hạn cần xử lý

Các trường hợp đáng chú ý:

- IllegalStateException: Publisher đã đóng và không còn nhận item mới.
- NullPointerException: item hoặc tham số bắt buộc là null.
- RejectedExecutionException: Executor từ chối tác vụ thông báo Subscriber.
- Exception từ onDrop: được truyền ra khỏi lời gọi offer.

Nếu Executor từ chối tác vụ khi đang thông báo Subscriber, exception có thể được ném ra và không phải mọi Subscriber đều đã nhận item. Đừng giả định một lần gọi offer có tính nguyên tử khi có lỗi từ Executor.

SubmissionPublisher có thể được chia sẻ cho nhiều producer. Hãy quản lý vòng đời Executor và Publisher rõ ràng; đóng Publisher trước khi kết thúc Executor để các tín hiệu terminal còn cơ hội được lập lịch.

close() gửi onComplete và không cho phép publish tiếp. Khi close() trả về, Subscriber chưa chắc đã chạy xong onComplete. Nếu ứng dụng phải đợi Subscriber kết thúc, dùng latch hoặc một cơ chế xác nhận terminal riêng.

## 12. Ví dụ hoàn chỉnh: buffer đầy và timed offer drop item

Ví dụ tạo một Subscriber không request dữ liệu. Item đầu tiên được đưa vào buffer; item thứ hai phải chờ tối đa 50 ms. Khi buffer vẫn đầy, drop handler ghi nhận item bị drop và trả về false.

**Tệp SubmissionOfferDemo.java:**

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

public class SubmissionOfferDemo {
    private static final class SlowSubscriber
            implements Flow.Subscriber<Integer> {
        private final CountDownLatch subscribed = new CountDownLatch(1);
        private volatile Flow.Subscription subscription;

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            subscribed.countDown();
        }

        @Override
        public void onNext(Integer item) {
            // Không request thêm: buffer sẽ giữ item chưa được tiêu thụ.
        }

        @Override
        public void onError(Throwable error) {
            throw new IllegalStateException(error);
        }

        @Override
        public void onComplete() {
        }

        void cancel() {
            subscription.cancel();
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        SubmissionPublisher<Integer> publisher =
                new SubmissionPublisher<>(executor, 1);
        SlowSubscriber subscriber = new SlowSubscriber();
        AtomicInteger dropped = new AtomicInteger();

        try {
            publisher.subscribe(subscriber);

            if (!subscriber.subscribed.await(2, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Subscriber was not subscribed");
            }

            int first = publisher.offer(
                    1,
                    0,
                    TimeUnit.MILLISECONDS,
                    (target, item) -> {
                        dropped.incrementAndGet();
                        return false;
                    });

            int second = publisher.offer(
                    2,
                    50,
                    TimeUnit.MILLISECONDS,
                    (target, item) -> {
                        dropped.incrementAndGet();
                        return false;
                    });

            System.out.println("first offer accepted: " + (first >= 0));
            System.out.println("second offer reported drops: " + (second < 0));
            System.out.println("second offer drop count: " + -second);
            System.out.println("drop handler calls: " + dropped.get());
        } finally {
            subscriber.cancel();
            publisher.close();
            executor.shutdown();

            if (!executor.awaitTermination(2, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }
}
~~~

Biên dịch với API Java 9 và chạy trên JDK 17 trở lên:

~~~bash
javac --release 9 -Xlint:all SubmissionOfferDemo.java
java SubmissionOfferDemo
~~~

Output:

~~~text
first offer accepted: true
second offer reported drops: true
second offer drop count: 1
drop handler calls: 1
~~~

Subscriber không gọi request nên item đầu tiên nằm trong buffer. Item thứ hai không có chỗ; timed offer chờ 50 ms rồi gọi handler. Handler trả về false nên item thứ hai bị drop đối với Subscriber đó. Cuối chương trình, Subscriber cancel để giải phóng đăng ký trước khi đóng Publisher và Executor.

Ví dụ kiểm tra chính sách drop ở cấp buffer. Trong ứng dụng thực tế, cần chọn dung lượng buffer, timeout và chính sách drop dựa trên tốc độ producer, tốc độ xử lý của Subscriber và mức độ quan trọng của dữ liệu.

## 13. Lỗi thường gặp

- **Coi offer là non-blocking trong mọi overload:** overload có timeout có thể chặn producer đến hết thời hạn.
- **Coi timeout là thời gian Subscriber xử lý:** timeout chỉ chờ tài nguyên buffer, không chờ onNext hoàn tất.
- **Bỏ qua giá trị âm:** giá trị âm biểu thị số lần drop; phải ghi nhận hoặc xử lý theo chính sách.
- **Cho rằng giá trị âm nghĩa là không Subscriber nào nhận item:** một số Subscriber có thể nhận trong khi Subscriber khác bị drop.
- **Cho rằng handler trả về true sẽ retry vô hạn:** SubmissionPublisher chỉ thử lại một lần.
- **Trả về true cho mọi drop:** có thể tạo thêm công việc nhưng không giải quyết buffer đầy.
- **Chặn lâu trong handler:** các lời gọi phương thức khác trên Publisher từ thread khác bị chặn khi handler đang chạy.
- **Dùng offer cho sự kiện không được phép mất:** offer không phải hàng đợi bền vững; chọn submit hoặc lưu trữ/retry phù hợp.
- **Dùng submit trên event loop:** buffer đầy có thể chặn thread quan trọng và gây nghẽn.
- **Dùng lag estimate làm điều kiện đồng bộ:** lag và demand chỉ là ước lượng phục vụ giám sát.
- **Không xử lý Executor rejection:** lỗi lập lịch có thể khiến một số Subscriber chưa nhận item.
- **Cho rằng close() đợi mọi Subscriber xử lý xong:** close gửi tín hiệu terminal nhưng không bảo đảm callback đã hoàn tất khi phương thức trả về.

## 14. Chọn API theo mục tiêu

| Mục tiêu | API |
|---|---|
| Không muốn bỏ item và chấp nhận producer chờ | submit(item) |
| Thử gửi ngay, drop nếu buffer đầy | offer(item, onDrop) |
| Chờ buffer trong thời gian giới hạn | offer(item, timeout, unit, onDrop) |
| Ghi metric theo Subscriber bị drop | onDrop BiPredicate |
| Yêu cầu thử lại đúng một lần | Handler trả về true |
| Chấp nhận drop item hiện tại | Handler trả về false |
| Kiểm tra số lần drop | Giá trị offer âm |
| Theo dõi độ trễ ước lượng | Giá trị offer không âm |
| Đóng Publisher bình thường | close() |
| Đóng Publisher bằng lỗi | closeExceptionally(error) |

## 15. Ghi nhớ

offer của SubmissionPublisher cho phép chọn cách xử lý khi buffer của Subscriber đầy. Overload không timeout thử gửi ngay; overload có timeout chờ tài nguyên trong thời hạn rồi gọi onDrop khi hết thời gian hoặc thread bị interrupt. Handler nhận Subscriber và item, trả về true để retry đúng một lần hoặc false để drop. Giá trị trả về âm là số lần drop, còn giá trị không âm là ước lượng lag lớn nhất. Vì buffer độc lập, một item có thể được gửi tới Subscriber nhanh nhưng bị drop ở Subscriber chậm. Dùng submit hoặc hàng đợi bền vững cho sự kiện không được mất; dùng offer khi chính sách drop đã được xác định rõ.

## 16. Tài liệu tham khảo

- [SubmissionPublisher – Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/SubmissionPublisher.html)
- [Flow – Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Flow.html)
