# Kiểm chứng giao thức khi lỗi, hủy hoặc bên nhận chậm

Flow trong Java 9 cung cấp các giao diện Reactive Streams trong `java.util.concurrent.Flow`. Một Publisher phát dữ liệu đến Subscriber thông qua Subscription. Để pipeline đáng tin cậy, cần kiểm tra cả đường đi bình thường lẫn ba tình huống khó: Publisher gặp lỗi, Subscriber hủy đăng ký và Subscriber tiêu thụ chậm hơn tốc độ phát.

Kiểm chứng giao thức không chỉ là xác nhận có nhận được dữ liệu. Cần bảo đảm đúng thứ tự tín hiệu, không phát vượt demand, không gửi tín hiệu sau khi kết thúc, tôn trọng hủy đăng ký và giữ bộ nhớ đệm trong giới hạn khi bên nhận chậm.

## 1. Các thành phần và hợp đồng tín hiệu

Flow định nghĩa bốn interface:

| Interface | Vai trò |
|---|---|
| `Flow.Publisher<T>` | Nguồn phát phần tử kiểu T |
| `Flow.Subscriber<T>` | Nhận subscription, phần tử và tín hiệu kết thúc |
| `Flow.Subscription` | Cho phép yêu cầu thêm dữ liệu hoặc hủy đăng ký |
| `Flow.Processor<T,R>` | Vừa nhận dữ liệu như Subscriber vừa phát dữ liệu như Publisher |

Subscriber nhận bốn callback:

~~~java
void onSubscribe(Flow.Subscription subscription);
void onNext(T item);
void onError(Throwable error);
void onComplete();
~~~

Subscription có hai thao tác:

~~~java
void request(long n);
void cancel();
~~~

Với một subscription, trình tự hợp lệ bắt đầu bằng `onSubscribe`, có thể tiếp tục với 0 hoặc nhiều `onNext`, rồi kết thúc bằng tối đa một trong hai tín hiệu `onError` hoặc `onComplete`.

Các quy tắc quan trọng để kiểm chứng:

- `onSubscribe` phải đến trước mọi callback khác của subscription.
- Publisher chỉ phát số phần tử phù hợp với demand chưa được đáp ứng.
- Các tín hiệu của cùng một subscription phải được tuần tự hóa, không gọi chồng lấn callback.
- `onError` và `onComplete` là terminal signal và loại trừ nhau.
- Sau terminal signal, không được phát thêm `onNext` hoặc terminal signal khác.
- `request(n)` yêu cầu n phải dương; request bằng 0 hoặc số âm là vi phạm giao thức.
- `cancel()` yêu cầu Publisher ngừng phát dữ liệu cho subscription đó.

Flow đảm bảo thứ tự tín hiệu, nhưng không bắt buộc mọi callback chạy trên cùng một thread. Publisher có thể đổi thread giữa các lần gọi nếu vẫn giữ đúng thứ tự và tuần tự hóa.

## 2. Kiểm chứng đường đi lỗi bằng onError

`onError(Throwable)` báo rằng Publisher hoặc Subscription gặp lỗi không thể tiếp tục phát dữ liệu bình thường. Đây là tín hiệu terminal.

Ví dụ, `SubmissionPublisher` có thể kết thúc bất thường bằng:

~~~java
publisher.closeExceptionally(
        new IllegalStateException("source failed")
);
~~~

Subscriber nhận `onError` sau những phần tử đã được phát theo thứ tự trước đó. Sau khi nhận `onError`, Subscriber không được nhận thêm `onNext` hoặc `onComplete` từ subscription đó.

Cần kiểm tra ít nhất các trường hợp:

1. Publisher lỗi trước khi phát phần tử nào.
2. Publisher phát một số phần tử rồi mới lỗi.
3. Publisher lỗi khi Subscriber đang xử lý hoặc đang có dữ liệu chờ.
4. Lỗi chỉ kết thúc subscription bị ảnh hưởng; các subscription độc lập khác phải tuân theo trạng thái riêng của chúng.

Không coi `onError` là một callback thông báo thông thường có thể tiếp tục phát dữ liệu sau đó. Nếu cần retry, ứng dụng thường tạo subscription hoặc pipeline mới theo chính sách retry.

### Request không hợp lệ cũng là lỗi giao thức

Flow quy định `request(n)` phải nhận giá trị dương. Với `n <= 0`, Subscriber sẽ nhận `onError` với `IllegalArgumentException`.

~~~java
@Override
public void onSubscribe(Flow.Subscription subscription) {
    subscription.request(0); // vi phạm: demand phải dương
}
~~~

Đây là tình huống hữu ích để kiểm thử Publisher có tuân thủ hợp đồng Flow hay không. Trong ứng dụng thực tế, không gửi request không hợp lệ; ví dụ trên chỉ dành cho kiểm thử đường đi lỗi.

## 3. Kiểm chứng hủy bằng cancel

Subscriber gọi `Subscription.cancel()` khi không còn muốn nhận dữ liệu:

~~~java
@Override
public void onNext(Integer item) {
    process(item);
    subscription.cancel();
}
~~~

Hủy là yêu cầu Publisher dừng phát tín hiệu. Nó không phải terminal signal và không có nghĩa Publisher phải gọi `onComplete` để xác nhận hủy.

Cancellation có tính bất đồng bộ. Publisher có thể đang xử lý hoặc đã đưa tín hiệu vào hàng đợi khi Subscriber gọi cancel. Vì vậy Subscriber cần thiết kế để xử lý an toàn một tín hiệu đã ở trạng thái in-flight theo hợp đồng của Publisher, đồng thời không tiếp tục yêu cầu dữ liệu sau khi đã hủy.

Các kiểm tra hữu ích:

- Hủy ngay trong `onSubscribe`, trước khi yêu cầu dữ liệu.
- Hủy trong `onNext` sau khi nhận một phần tử.
- Hủy khi có dữ liệu đang chờ trong buffer.
- Sau khi hủy, xác nhận Publisher ngừng phát các phần tử tiếp theo trong điều kiện kiểm thử đã đồng bộ.
- Không đòi hỏi `onComplete` hoặc `onError` như một xác nhận bắt buộc sau cancel.

Nếu Subscriber không còn cần dữ liệu, hãy hủy sớm để tránh tiếp tục tiêu thụ tài nguyên. Nếu ứng dụng cần một tín hiệu hoàn tất nghiệp vụ riêng, hãy quản lý tín hiệu đó ở tầng ứng dụng; đừng nhầm nó với terminal callback của Flow.

## 4. Bên nhận chậm và backpressure

Backpressure là cơ chế để Subscriber kiểm soát tốc độ phát thông qua demand:

~~~java
subscription.request(5);
~~~

Publisher có thể phát tối đa năm phần tử theo demand đó. Khi Subscriber xử lý chậm, demand chưa được bổ sung sẽ khiến Publisher không thể tiếp tục gửi `onNext` vượt số lượng đã yêu cầu.

Điều này giúp kiểm soát tốc độ ở ranh giới Publisher/Subscriber, nhưng không tự động bảo vệ mọi queue do ứng dụng tạo ra. Nếu Subscriber request không giới hạn rồi đẩy toàn bộ dữ liệu vào một queue không giới hạn, bộ nhớ vẫn có thể tăng không kiểm soát.

Một Subscriber xử lý theo từng phần có thể request thêm sau khi đã xử lý xong:

~~~java
@Override
public void onNext(Item item) {
    process(item);
    subscription.request(1);
}
~~~

Mô hình này duy trì lượng công việc đang được yêu cầu ở mức nhỏ. Nếu việc xử lý được chuyển sang executor khác, chỉ request thêm khi queue nội bộ còn khả năng tiếp nhận.

## 5. SubmissionPublisher: buffer, submit và offer

Java 9 cung cấp `SubmissionPublisher<T>`, một triển khai Publisher có buffer cho từng Subscriber và hỗ trợ phát bất đồng bộ.

~~~java
SubmissionPublisher<Integer> publisher =
        new SubmissionPublisher<>(executor, 16);
~~~

Tham số thứ hai là dung lượng buffer tối đa cho mỗi Subscriber. Implementation có thể làm tròn dung lượng thực tế theo yêu cầu nội bộ; không nên xem nó là số phần tử chính xác sẽ luôn được cấp phát.

Hai cách phát dữ liệu có hành vi khác nhau:

| API | Khi buffer của Subscriber đầy |
|---|---|
| `submit(item)` | Có thể chặn thread gọi cho đến khi có chỗ |
| `offer(item, onDrop)` | Không chờ vô hạn; gọi drop handler khi không thể xếp hàng |

`submit` phù hợp khi ứng dụng chấp nhận backpressure bằng cách làm chậm thread phát. Nếu thread gọi là UI thread hoặc thread phục vụ request quan trọng, việc bị chặn có thể gây vấn đề về độ trễ.

`offer` trả về ước lượng độ trễ tối đa của các Subscriber. Giá trị âm cho biết item đã bị bỏ cho ít nhất một Subscriber. Drop handler quyết định có thử lại hay bỏ item:

~~~java
int lag = publisher.offer(item, (subscriber, droppedItem) -> {
    recordDrop(droppedItem);
    return false; // bỏ item cho Subscriber đang đầy buffer
});
~~~

Nếu handler trả về `true`, SubmissionPublisher thử lại việc offer cho Subscriber bị đầy; nếu trả về `false`, item bị bỏ cho Subscriber đó. Cần chọn chính sách rõ ràng: bỏ dữ liệu, thử lại có giới hạn hoặc chuyển sang một cơ chế lưu trữ khác.

Không dùng `offer` rồi bỏ qua kết quả trả về. Nếu dữ liệu không được phép mất, phải phát hiện tình huống drop và xử lý theo yêu cầu nghiệp vụ.

## 6. Kiểm thử Subscriber chậm có kiểm soát

Một kịch bản kiểm thử có thể tạo Subscriber chỉ request một phần tử:

1. Subscriber request đúng một item trong `onSubscribe`.
2. Publisher phát item đầu tiên; Subscriber nhận và không request thêm.
3. Publisher đưa item tiếp theo vào buffer.
4. Publisher offer thêm item khi buffer đầy; drop handler được gọi.
5. Subscriber request thêm một item và nhận phần tử còn chờ.

Kịch bản này kiểm tra được backpressure và chính sách overflow mà không cần giả định tốc độ CPU hay dùng `Thread.sleep`.

Với `SubmissionPublisher`, nên dùng latch để chờ sự kiện thực tế như `onNext` hoặc terminal callback. Tránh dùng sleep cố định để đoán callback đã chạy, vì timing phụ thuộc scheduler và tải hệ thống.

## 7. Kiểm tra các bất biến của protocol

Khi viết test cho Publisher hoặc Subscriber, nên ghi lại trace các tín hiệu và kiểm tra các bất biến:

| Bất biến | Cách kiểm tra |
|---|---|
| onSubscribe đến trước | Không có onNext/onError/onComplete trước onSubscribe |
| Không vượt demand | Số onNext không vượt tổng request chưa tiêu thụ |
| Tín hiệu tuần tự | Không có hai callback của cùng subscription chạy chồng lấn |
| Chỉ một terminal signal | Không nhận cả onError và onComplete |
| Terminal là cuối cùng | Không có onNext sau terminal |
| Hủy có hiệu lực | Publisher ngừng phát sau khi xử lý yêu cầu cancel |
| Buffer có giới hạn | Subscriber chậm không làm queue tăng vô hạn |
| Drop được quan sát | Mọi lần offer bị drop đều được ghi nhận hoặc xử lý |

Một trace đơn giản có thể là:

~~~text
onSubscribe
onNext(10)
onNext(20)
onError(source failed)
~~~

Trace này hợp lệ vì `onSubscribe` xuất hiện trước, các phần tử nằm trong demand, và `onError` là tín hiệu terminal duy nhất.

Trace sau không hợp lệ:

~~~text
onSubscribe
onComplete
onNext(30)
~~~

Không được phát dữ liệu sau khi subscription đã hoàn tất.

## 8. Xử lý exception bên trong Subscriber

`onError` là tín hiệu lỗi do Publisher gửi. Nó không phải cơ chế tự động bắt mọi exception phát sinh trong code của Subscriber.

Nếu `onNext` ném exception, không nên kỳ vọng Publisher luôn chuyển exception đó thành `onError` cho chính Subscriber. Hành vi khi Subscriber ném exception từ callback không được bảo đảm như một đường xử lý lỗi thông thường.

Subscriber nên tự xử lý lỗi nghiệp vụ trong callback:

~~~java
@Override
public void onNext(Item item) {
    try {
        process(item);
    } catch (RuntimeException error) {
        subscription.cancel();
        reportProcessingFailure(error);
    }
}
~~~

Nếu lỗi xử lý cần được truyền đến một tầng khác, hãy gửi nó qua cơ chế lỗi của ứng dụng. Hủy subscription khi không thể tiếp tục tiêu thụ dữ liệu.

## 9. Ví dụ chạy được với Java 17+

Tạo file **FlowProtocolValidationDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

public class FlowProtocolValidationDemo {
    static class RecordingSubscriber implements Flow.Subscriber<Integer> {
        final List<String> signals = new ArrayList<>();
        final boolean cancelOnFirst;
        Flow.Subscription subscription;

        RecordingSubscriber(boolean cancelOnFirst) {
            this.cancelOnFirst = cancelOnFirst;
        }

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            signals.add("onSubscribe");
            subscription.request(cancelOnFirst ? 1 : Long.MAX_VALUE);
        }

        @Override
        public void onNext(Integer item) {
            signals.add("onNext: " + item);
            if (cancelOnFirst) {
                subscription.cancel();
            }
        }

        @Override
        public void onError(Throwable error) {
            signals.add("onError: " + error.getMessage());
        }

        @Override
        public void onComplete() {
            signals.add("onComplete");
        }
    }

    static class SlowSubscriber implements Flow.Subscriber<Integer> {
        volatile Flow.Subscription subscription;
        final CountDownLatch firstItem = new CountDownLatch(1);
        final CountDownLatch secondItem = new CountDownLatch(1);
        final CountDownLatch terminal = new CountDownLatch(1);

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            subscription.request(1);
        }

        @Override
        public void onNext(Integer item) {
            if (item == 10) {
                firstItem.countDown();
            } else if (item == 20) {
                secondItem.countDown();
            }
        }

        @Override
        public void onError(Throwable error) {
            terminal.countDown();
        }

        @Override
        public void onComplete() {
            terminal.countDown();
        }
    }

    static void exceptionalTermination() {
        try (SubmissionPublisher<Integer> publisher =
                     new SubmissionPublisher<>(Runnable::run, 8)) {
            RecordingSubscriber subscriber = new RecordingSubscriber(false);
            publisher.subscribe(subscriber);
            publisher.submit(7);
            publisher.closeExceptionally(
                    new IllegalStateException("source failed")
            );

            System.out.println("error signals: " + subscriber.signals);
        }
    }

    static void invalidDemand() {
        try (SubmissionPublisher<Integer> publisher =
                     new SubmissionPublisher<>(Runnable::run, 8)) {
            publisher.subscribe(new Flow.Subscriber<Integer>() {
                @Override
                public void onSubscribe(Flow.Subscription subscription) {
                    subscription.request(0);
                }

                @Override
                public void onNext(Integer item) {
                    throw new AssertionError("No item expected");
                }

                @Override
                public void onError(Throwable error) {
                    System.out.println("invalid demand: "
                            + error.getClass().getSimpleName());
                }

                @Override
                public void onComplete() {
                    throw new AssertionError("No completion expected");
                }
            });
        }
    }

    static void cancellation() {
        try (SubmissionPublisher<Integer> publisher =
                     new SubmissionPublisher<>(Runnable::run, 8)) {
            RecordingSubscriber subscriber = new RecordingSubscriber(true);
            publisher.subscribe(subscriber);
            publisher.submit(1);
            publisher.submit(2);
            publisher.close();

            System.out.println("cancel signals: " + subscriber.signals);
        }
    }

    static void slowSubscriber() throws InterruptedException {
        ExecutorService executor = Executors.newSingleThreadExecutor();
        try (SubmissionPublisher<Integer> publisher =
                     new SubmissionPublisher<>(executor, 1)) {
            SlowSubscriber subscriber = new SlowSubscriber();
            publisher.subscribe(subscriber);

            publisher.submit(10);
            if (!subscriber.firstItem.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("first item timed out");
            }

            int acceptedLag = publisher.offer(20, (target, item) -> false);
            AtomicBoolean dropped = new AtomicBoolean();
            int droppedLag = publisher.offer(30, (target, item) -> {
                dropped.set(true);
                return false;
            });

            if (acceptedLag < 0 || droppedLag >= 0 || !dropped.get()) {
                throw new AssertionError("Unexpected offer/drop result: "
                        + acceptedLag + ", " + droppedLag);
            }

            System.out.println("slow first: 10");
            System.out.println("offer dropped: 30");

            subscriber.subscription.request(1);
            if (!subscriber.secondItem.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("second item timed out");
            }

            publisher.close();
            if (!subscriber.terminal.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("terminal signal timed out");
            }
            System.out.println("slow second: 20");
            System.out.println("slow terminal: complete");
        } finally {
            executor.shutdown();
            if (!executor.awaitTermination(5, TimeUnit.SECONDS)) {
                executor.shutdownNow();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        exceptionalTermination();
        invalidDemand();
        cancellation();
        slowSubscriber();
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac FlowProtocolValidationDemo.java
java FlowProtocolValidationDemo
~~~

Kết quả stdout:

~~~text
error signals: [onSubscribe, onNext: 7, onError: source failed]
invalid demand: IllegalArgumentException
cancel signals: [onSubscribe, onNext: 1]
slow first: 10
offer dropped: 30
slow second: 20
slow terminal: complete
~~~

Giải thích:

- Đường lỗi phát một item rồi kết thúc bằng `onError`; không có `onComplete`.
- Request bằng 0 tạo `onError(IllegalArgumentException)`.
- Subscriber hủy ngay sau item đầu tiên nên không nhận item thứ hai hoặc terminal callback.
- Subscriber chậm chỉ request một item. Item 20 nằm trong buffer, item 30 bị drop khi buffer đầy. Sau khi request thêm, item 20 được giao và Publisher hoàn tất.

Ví dụ dùng executor trực tiếp cho các trường hợp lỗi và hủy để trace callback dễ quan sát. Kịch bản Subscriber chậm dùng executor riêng và latch để đồng bộ với callback thật, không dựa vào thời gian ngủ cố định.

## 10. Lỗi thường gặp khi kiểm chứng

**Chỉ kiểm tra dữ liệu mà không kiểm tra thứ tự:** cần xác nhận onSubscribe đầu tiên và terminal signal là cuối cùng.

**Cho rằng onError có thể theo sau bởi onComplete:** hai terminal signal loại trừ nhau trên cùng subscription.

**Coi cancel là onComplete:** cancel là yêu cầu dừng, không phải tín hiệu hoàn tất bình thường.

**Request không giới hạn cho Subscriber chậm:** điều này có thể khiến dữ liệu tích tụ trong queue nội bộ của ứng dụng. Điều chỉnh demand theo năng lực tiêu thụ.

**Dùng submit trên thread không được phép chặn:** submit có thể chờ khi buffer đầy. Chọn offer hoặc kiến trúc phát phù hợp nếu thread gọi cần tiếp tục đáp ứng công việc khác.

**Dùng offer nhưng bỏ qua giá trị âm:** giá trị âm báo đã có item bị drop cho ít nhất một Subscriber. Ghi nhận và áp dụng chính sách mất dữ liệu rõ ràng.

**Giả định cancel dừng mọi callback tức thời:** cancellation có thể cạnh tranh với tín hiệu đang được gửi. Thiết kế callback an toàn với trạng thái hủy.

**Dùng Thread.sleep để chờ callback trong test:** dùng CountDownLatch, CompletableFuture hoặc cơ chế đồng bộ hóa xác định để test ổn định.

**Để exception thoát khỏi onNext:** Subscriber phải tự xử lý lỗi trong callback và cancel hoặc báo lỗi ở tầng ứng dụng nếu không thể tiếp tục.

## 11. Checklist kiểm chứng

- Ghi trace tất cả callback theo từng subscription.
- Xác nhận onSubscribe đến trước onNext và terminal signal.
- Kiểm tra số onNext không vượt demand.
- Kiểm tra request bằng 0 hoặc số âm dẫn đến onError.
- Kiểm tra onError và onComplete loại trừ nhau.
- Kiểm tra không có tín hiệu sau terminal signal.
- Kiểm tra cancel khi chưa nhận dữ liệu và cancel trong onNext.
- Kiểm tra Publisher ngừng phát sau khi xử lý cancel.
- Kiểm tra Subscriber chậm với buffer có giới hạn.
- Kiểm tra submit có thể chặn và offer có thể drop.
- Kiểm tra drop handler và giá trị trả về âm của offer.
- Dùng latch hoặc future để đồng bộ test thay cho sleep.
- Xử lý exception phát sinh trong callback của Subscriber.

Flow yêu cầu một giao thức rõ ràng: Subscriber đăng ký, yêu cầu dữ liệu, nhận các phần tử trong phạm vi demand và kết thúc bằng một terminal signal. Kiểm thử lỗi, hủy và bên nhận chậm giúp xác nhận Publisher tuân thủ giao thức, giới hạn bộ nhớ đệm và xử lý đúng các tình huống bất thường.
