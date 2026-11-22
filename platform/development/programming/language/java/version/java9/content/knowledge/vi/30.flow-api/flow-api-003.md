# Trình tự onSubscribe, onNext, onError và onComplete

Java 9 đưa Reactive Streams interfaces vào JDK dưới package `java.util.concurrent.Flow`. Mô hình này mô tả cách một Publisher phát dữ liệu đến Subscriber thông qua một Subscription. Bốn callback `onSubscribe`, `onNext`, `onError` và `onComplete` tạo thành vòng đời tín hiệu của một subscription.

Hiểu đúng thứ tự callback giúp tránh xử lý dữ liệu trước khi đăng ký, phát vượt nhu cầu, gửi tín hiệu sau khi đã kết thúc hoặc xử lý lỗi như một lần hoàn tất bình thường.

## 1. Các thành phần của Flow

Flow định nghĩa bốn interface chính:

| Interface | Vai trò |
|---|---|
| `Flow.Publisher<T>` | Nguồn phát các phần tử kiểu T đến Subscriber |
| `Flow.Subscriber<T>` | Nhận subscription, dữ liệu và tín hiệu kết thúc |
| `Flow.Subscription` | Cầu nối điều khiển nhu cầu và hủy đăng ký |
| `Flow.Processor<T,R>` | Vừa là Subscriber đầu vào vừa là Publisher đầu ra |

Publisher đăng ký Subscriber bằng:

~~~java
void subscribe(Flow.Subscriber<? super T> subscriber)
~~~

Subscriber nhận bốn callback:

~~~java
void onSubscribe(Flow.Subscription subscription);
void onNext(T item);
void onError(Throwable throwable);
void onComplete();
~~~

Subscription cung cấp hai thao tác điều khiển:

~~~java
void request(long n);
void cancel();
~~~

Publisher quyết định khi nào có dữ liệu, còn Subscriber thông báo số lượng phần tử mình sẵn sàng nhận thông qua `request(n)`. Đây là cơ chế backpressure của Flow.

## 2. Trình tự tín hiệu chuẩn

Với mỗi subscription, trình tự tổng quát là:

~~~text
onSubscribe(subscription)
        |
        v
   onNext(item) 0..N lần
        |
        +--------------------+
        |                    |
        v                    v
   onComplete()           onError(error)
      (hoặc)                 (hoặc)
~~~

Các quy tắc quan trọng:

1. `onSubscribe` phải được gọi trước mọi callback khác của subscription đó.
2. Sau `onSubscribe`, Publisher có thể gửi 0 hoặc nhiều lần `onNext`, tùy nhu cầu đã được request.
3. Subscription kết thúc bằng tối đa một tín hiệu terminal: `onComplete` hoặc `onError`.
4. `onComplete` và `onError` loại trừ nhau; một subscription không được gửi cả hai như hai tín hiệu kết thúc liên tiếp.
5. Sau tín hiệu terminal, không được gửi thêm `onNext` hoặc tín hiệu terminal khác.
6. Các callback của cùng một Subscriber phải được tuần tự hóa: một callback trước phải hoàn tất trước khi callback tiếp theo được gọi.

Do đó, một subscription có thể kết thúc bình thường mà không phát phần tử nào: `onSubscribe` rồi `onComplete`. Nó cũng có thể kết thúc lỗi trước khi phát bất kỳ `onNext` nào: `onSubscribe` rồi `onError`.

## 3. onSubscribe: bắt đầu subscription

`onSubscribe` thông báo Publisher đã tạo một subscription và trao cho Subscriber đối tượng điều khiển đó.

Đây là nơi thường lưu Subscription và yêu cầu dữ liệu:

~~~java
@Override
public void onSubscribe(Flow.Subscription subscription) {
    this.subscription = subscription;
    subscription.request(5);
}
~~~

Nếu Subscriber không gọi `request`, Publisher không có nhu cầu dương để phát `onNext`. Subscriber cũng có thể hủy ngay trong callback:

~~~java
@Override
public void onSubscribe(Flow.Subscription subscription) {
    subscription.cancel();
}
~~~

Sau khi hủy, Publisher được yêu cầu ngừng phát tín hiệu cho subscription đó. Việc dừng có thể không xảy ra ngay lập tức nếu một tín hiệu đã được gửi hoặc đang được xử lý.

Không giả định `onSubscribe` luôn chạy trên thread gọi `subscribe`. Publisher có thể thực thi callback trên executor riêng; hãy tuân theo hợp đồng đồng bộ hóa của Publisher.

## 4. onNext: nhận một phần tử

`onNext(T item)` được gọi khi Publisher phát một phần tử. Mỗi lần gọi tương ứng một phần tử được chuyển đến Subscriber.

~~~java
@Override
public void onNext(Integer item) {
    System.out.println("received: " + item);
}
~~~

Publisher chỉ được phát số phần tử phù hợp với demand mà Subscriber đã yêu cầu và chưa tiêu thụ. Nếu Subscriber gọi `request(3)`, Publisher có thể phát tối đa ba phần tử theo nhu cầu đó trước khi cần thêm request.

Không giả định một lần `request(n)` luôn tạo ra đúng n lần `onNext`: Publisher có thể hoàn tất, gặp lỗi hoặc không còn phần tử trước khi phát đủ số lượng.

`onNext` nên xử lý nhanh và không chặn không cần thiết. Nếu xử lý tốn thời gian, có thể chuyển công việc sang executor riêng, nhưng cần kiểm soát thứ tự và bộ nhớ đệm để không làm mất backpressure.

## 5. onError: tín hiệu kết thúc do lỗi

`onError(Throwable throwable)` thông báo Publisher không thể tiếp tục phát dữ liệu bình thường. Đây là tín hiệu terminal.

~~~java
@Override
public void onError(Throwable throwable) {
    System.err.println("stream failed: " + throwable.getMessage());
}
~~~

Sau `onError`, Publisher không được tiếp tục gọi `onNext` hoặc `onComplete` cho subscription đó.

Subscriber nên xử lý lỗi tại đây: ghi log, hoàn tất tài nguyên, thông báo trạng thái thất bại hoặc chuyển lỗi đến tầng điều phối. Không xem `onError` như một callback thông thường có thể theo sau bằng dữ liệu mới trên cùng subscription.

Nếu cần thử lại, ứng dụng thường tạo subscription hoặc pipeline mới theo chính sách retry. Không yêu cầu Publisher tiếp tục phát trên subscription đã kết thúc lỗi.

## 6. onComplete: kết thúc bình thường

`onComplete()` thông báo Publisher đã phát xong dữ liệu và không còn phần tử nào cho subscription đó.

~~~java
@Override
public void onComplete() {
    System.out.println("stream completed");
}
~~~

Đây cũng là tín hiệu terminal. Sau `onComplete`, Subscriber không được chờ thêm `onNext` trên cùng subscription.

Một Publisher có thể gọi `onComplete` ngay sau `onSubscribe` nếu nguồn rỗng. Nếu nguồn có dữ liệu, nó thường phát các `onNext` đã được request rồi mới phát `onComplete`.

Phân biệt hai trường hợp:

- `onComplete`: nguồn kết thúc bình thường.
- `onError`: nguồn kết thúc do lỗi.

Không suy luận thành công chỉ từ việc không còn thấy `onNext`; hãy đợi tín hiệu terminal hoặc quản lý timeout ở tầng ứng dụng.

## 7. Backpressure: request và cancel

Flow dùng `Subscription.request(long n)` để Subscriber điều khiển số phần tử muốn nhận.

~~~java
subscription.request(1);
subscription.request(4);
~~~

Hai lời gọi cộng dồn demand chưa được đáp ứng. Subscriber có thể request thêm trong `onNext` sau khi xử lý một phần tử:

~~~java
@Override
public void onNext(Item item) {
    process(item);
    subscription.request(1);
}
~~~

Một số quy tắc:

- `n` phải lớn hơn 0.
- Request với số không dương vi phạm hợp đồng; Subscriber sẽ nhận tín hiệu `onError` với `IllegalArgumentException` theo đặc tả Flow.
- Demand có thể cộng dồn; implementation cần xử lý tràn khi cộng nhu cầu và thường bão hòa ở `Long.MAX_VALUE`.
- `request(Long.MAX_VALUE)` thể hiện nhu cầu không giới hạn thực tế; chỉ dùng khi Subscriber có khả năng tiếp nhận và xử lý tốc độ phát.

`cancel()` yêu cầu Publisher ngừng phát dữ liệu cho subscription:

~~~java
subscription.cancel();
~~~

Cancel không phải tín hiệu terminal gửi đến Subscriber. Sau cancel, Subscriber không được trông chờ `onComplete` hoặc `onError` như một xác nhận hủy. Publisher có thể đã có tín hiệu đang được gửi tại thời điểm hủy, nên không coi cancel là một hàng rào đồng bộ tức thời.

## 8. Thứ tự callback và xử lý đồng thời

Flow yêu cầu các tín hiệu gửi đến cùng một Subscriber được tuần tự hóa. Một callback trước phải hoàn tất trước khi callback kế tiếp bắt đầu; thứ tự tín hiệu được duy trì ngay cả khi Publisher dùng nhiều thread nội bộ.

Điều đó không có nghĩa mọi callback luôn chạy trên cùng một thread. Publisher có thể đổi thread giữa các lần gọi nhưng vẫn phải giữ thứ tự và quan hệ happens-before cần thiết.

Subscriber nên tránh:

- Giữ khóa lâu trong `onNext` khiến Publisher bị chặn.
- Gọi xử lý đồng bộ nặng trong callback.
- Giả định callback luôn chạy trên UI thread hoặc thread gọi subscribe.
- Tự tạo nhiều thread xử lý item rồi hoàn tất không theo thứ tự khi nghiệp vụ cần thứ tự nguồn.

Nếu chuyển xử lý sang executor riêng, cần giới hạn queue hoặc điều chỉnh request theo khả năng tiêu thụ. Nếu request toàn bộ nhưng đưa mọi item vào một queue không giới hạn, backpressure ở ranh giới Flow sẽ không còn bảo vệ được bộ nhớ của ứng dụng.

## 9. SubmissionPublisher: Publisher có sẵn trong JDK

Java 9 cung cấp `SubmissionPublisher<T>`, một triển khai Publisher có thể phát dữ liệu bất đồng bộ đến các Subscriber.

Ví dụ:

~~~java
try (SubmissionPublisher<Integer> publisher =
         new SubmissionPublisher<>()) {
    publisher.subscribe(subscriber);
    publisher.submit(10);
    publisher.submit(20);
    publisher.close();
}
~~~

- `subscribe` đăng ký Subscriber.
- `submit` gửi phần tử đến các Subscriber đã đăng ký; lời gọi có thể chờ khi buffer bị đầy.
- `close()` kết thúc Publisher bình thường; Subscriber nhận `onComplete` sau khi dữ liệu đã được xử lý theo hợp đồng.
- `closeExceptionally(error)` kết thúc Publisher với lỗi và dẫn đến `onError`.

SubmissionPublisher sử dụng executor để phân phối tín hiệu. Subscriber phải request để nhận dữ liệu; nếu không có demand, dữ liệu có thể nằm trong buffer cho đến khi được yêu cầu hoặc chính sách buffer được áp dụng.

## 10. Ví dụ chạy được với Java 17+

Tạo file **FlowSignalOrderDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;

public class FlowSignalOrderDemo {
    static class LoggingSubscriber implements Flow.Subscriber<Integer> {
        private final CountDownLatch completed = new CountDownLatch(1);

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            System.out.println("onSubscribe");
            subscription.request(3);
        }

        @Override
        public void onNext(Integer item) {
            System.out.println("onNext: " + item);
        }

        @Override
        public void onError(Throwable error) {
            System.out.println("onError: "
                    + error.getClass().getSimpleName());
            completed.countDown();
        }

        @Override
        public void onComplete() {
            System.out.println("onComplete");
            completed.countDown();
        }

        void awaitCompletion() throws InterruptedException {
            if (!completed.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Timed out waiting for terminal signal"
                );
            }
        }
    }

    public static void main(String[] args) throws Exception {
        try (SubmissionPublisher<Integer> publisher =
                     new SubmissionPublisher<>(Runnable::run, 8)) {
            LoggingSubscriber subscriber = new LoggingSubscriber();
            publisher.subscribe(subscriber);

            publisher.submit(10);
            publisher.submit(20);
            publisher.submit(30);
            publisher.close();

            subscriber.awaitCompletion();
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FlowSignalOrderDemo.java
java FlowSignalOrderDemo
~~~

Kết quả stdout:

~~~text
onSubscribe
onNext: 10
onNext: 20
onNext: 30
onComplete
~~~

Subscriber request ba phần tử trong `onSubscribe`, vì vậy Publisher có thể phát ba lần `onNext`. Sau khi Publisher đóng bình thường, Subscriber nhận `onComplete`. CountDownLatch giữ thread main chờ tín hiệu terminal thay vì kết thúc chương trình quá sớm.

Ví dụ dùng executor trực tiếp `Runnable::run` để làm thứ tự callback dễ quan sát. Trong ứng dụng thực tế, SubmissionPublisher thường chạy bất đồng bộ trên executor phù hợp.

## 11. Ví dụ kết thúc bằng onError

SubmissionPublisher có thể kết thúc bất thường:

~~~java
publisher.closeExceptionally(
        new IllegalStateException("source failed")
);
~~~

Subscriber nhận `onError` thay cho `onComplete`. Với subscription đó, sau khi `onError` được gửi thì không còn `onNext` hoặc terminal signal nào khác.

Không gọi `close()` sau `closeExceptionally()` để mong có thêm `onComplete`; subscription đã đi vào trạng thái terminal do lỗi.

## 12. Lỗi thường gặp

**Không request trong onSubscribe:** Subscriber không tạo demand nên không nhận được phần tử. Hãy lưu Subscription và request số lượng phù hợp.

**Nhầm onError với onComplete:** đây là hai terminal signal loại trừ nhau. Lỗi không phải kết thúc bình thường.

**Gửi hoặc xử lý dữ liệu sau terminal signal:** sau onError hoặc onComplete, subscription đã kết thúc; không được phát thêm onNext.

**Request số không hoặc số âm:** request phải dương; giá trị không hợp lệ dẫn đến onError theo hợp đồng Flow.

**Cho rằng cancel sẽ gọi onComplete:** cancel yêu cầu dừng subscription, không phải yêu cầu Publisher phát tín hiệu hoàn tất bình thường.

**Cho rằng callback luôn chạy trên cùng thread:** Flow đảm bảo thứ tự và tuần tự hóa tín hiệu, không bắt buộc một thread cố định.

**Request không giới hạn nhưng xử lý chậm:** demand lớn không tự làm consumer nhanh hơn. Kiểm soát số lượng yêu cầu và bộ nhớ đệm theo khả năng xử lý.

**Chuyển item sang queue không giới hạn:** queue có thể tăng vô hạn dù Publisher tuân thủ backpressure. Giới hạn queue và điều phối request theo lượng công việc đang chờ.

## 13. Checklist đọc vòng đời Subscriber

- Xác nhận `onSubscribe` xuất hiện đầu tiên.
- Trong `onSubscribe`, lưu Subscription và request nhu cầu phù hợp hoặc cancel.
- Xử lý mỗi `onNext` như một phần tử dữ liệu; không giả định luôn nhận đủ số đã request.
- Xử lý `onError` như kết thúc lỗi.
- Xử lý `onComplete` như kết thúc bình thường.
- Không chờ thêm tín hiệu sau terminal callback.
- Giữ callback ngắn và duy trì backpressure khi chuyển xử lý sang executor khác.
- Không giả định callback chạy trên cùng một thread.
- Dùng `SubmissionPublisher` hoặc một Publisher tuân thủ Flow để phát tín hiệu đúng hợp đồng.

Flow định nghĩa vòng đời rõ ràng: `onSubscribe` mở đầu, `onNext` truyền dữ liệu theo demand, và đúng một trong hai tín hiệu `onError` hoặc `onComplete` kết thúc subscription. Nắm chắc trình tự này là nền tảng để xây dựng Publisher, Subscriber và pipeline bất đồng bộ an toàn.
