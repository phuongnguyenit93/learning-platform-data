# Trình tự onSubscribe, onNext, onError và onComplete trong Reactive Streams

## 1. Mục tiêu và bối cảnh

Reactive Streams quy định cách một **Publisher** (nguồn phát) gửi dữ liệu cho **Subscriber** (bên nhận) một cách bất đồng bộ, có kiểm soát tốc độ nhận bằng **backpressure**. Trong Spring WebFlux, Reactor (**Flux**, **Mono**) triển khai mô hình này. Để đọc log, viết Subscriber hoặc xử lý lỗi đúng, cần hiểu thứ tự của bốn callback:

- **onSubscribe(Subscription)**: thiết lập quyền điều khiển luồng dữ liệu.
- **onNext(T)**: chuyển một phần tử dữ liệu.
- **onError(Throwable)**: thông báo luồng thất bại và kết thúc.
- **onComplete()**: thông báo luồng hoàn thành thành công và kết thúc.

Bốn callback là **tín hiệu gửi đến Subscriber**. Hai thao tác **Subscription.request(n)** và **Subscription.cancel()** đi theo chiều ngược lại, từ Subscriber đến Publisher; chúng điều khiển nhu cầu nhận và việc hủy đăng ký.

## 2. Giao thức thứ tự: một khởi đầu, không hoặc nhiều phần tử, tối đa một kết thúc

Chuỗi callback hợp lệ được mô tả bằng biểu thức:

~~~text
onSubscribe → onNext* → (onError | onComplete)?
~~~

Ý nghĩa của các ký hiệu:

- **onSubscribe** đến trước mọi callback khác và được gọi tối đa một lần cho một Subscriber.
- Dấu **\*** nghĩa là có thể có 0, 1 hoặc nhiều **onNext**; mỗi lần mang đúng một phần tử.
- Dấu **|** nghĩa là một luồng chỉ kết thúc bằng **onError** *hoặc* **onComplete**, không thể bằng cả hai.
- Dấu **?** nghĩa là tại một thời điểm quan sát, có thể chưa có tín hiệu kết thúc: luồng còn hoạt động, là luồng vô hạn hoặc đã được hủy bằng **cancel()**. Nếu một nguồn hữu hạn hoàn thành bình thường, nó phải phát **onComplete**; nếu nguồn thất bại, nó phải báo **onError**.

Các đường đi thường gặp:

~~~text
Thành công có dữ liệu:
onSubscribe → onNext(A) → onNext(B) → onComplete

Nguồn rỗng:
onSubscribe → onComplete

Lỗi trước khi có dữ liệu:
onSubscribe → onError(error)

Lỗi giữa chừng:
onSubscribe → onNext(A) → onError(error)

Được hủy khi đang chạy:
onSubscribe → onNext(A) → cancel()
(có thể không có onComplete/onError; tín hiệu đang truyền vẫn có thể tới)
~~~

**Không hợp lệ:** gọi **onNext** trước **onSubscribe**; gọi **onComplete** rồi **onError**; gọi **onNext** sau một tín hiệu kết thúc; gửi hai tín hiệu kết thúc; phát hai **onSubscribe** cho cùng Subscriber; hoặc phát **onNext** vượt quá nhu cầu đã được yêu cầu.

## 3. Ý nghĩa của từng callback

| Callback | Khi nào xuất hiện? | Subscriber nên làm gì? | Sau callback còn gì? |
| --- | --- | --- | --- |
| **onSubscribe(Subscription s)** | Đầu quan hệ đăng ký, trước mọi callback khác | Lưu Subscription; gọi **s.request(n)** với **n > 0** khi sẵn sàng nhận; hoặc **s.cancel()** nếu không cần | Có thể tiếp tục bằng **onNext**, **onError**, **onComplete** |
| **onNext(T item)** | Có một phần tử sẵn sàng **và** còn nhu cầu nhận | Xử lý phần tử; yêu cầu thêm khi đủ khả năng | Có thể còn **onNext** khác hoặc một tín hiệu kết thúc |
| **onError(Throwable error)** | Publisher/Subscription gặp lỗi không thể tiếp tục | Ghi nhận, báo lỗi, dọn dẹp tài nguyên thuộc Subscriber | **Kết thúc**; không có callback nào tiếp theo trên cùng Subscription |
| **onComplete()** | Nguồn hữu hạn phát hết dữ liệu và kết thúc thành công | Hoàn tất xử lý, dọn dẹp tài nguyên thuộc Subscriber | **Kết thúc**; không có callback nào tiếp theo trên cùng Subscription |

**onSubscribe** là callback do Publisher gọi khi đăng ký; nó khác với lời gọi **publisher.subscribe(subscriber)** của người dùng. Đối tượng **Subscription** được truyền đến callback, không phải giá trị trả về từ **subscribe**.

**onNext** không đồng nghĩa với "Publisher có dữ liệu là lập tức đẩy": Publisher chỉ được phát tối đa số phần tử mà Subscriber đã yêu cầu. Theo hợp đồng Reactive Streams, giá trị phần tử được gửi không được là **null**; biểu diễn luồng không có phần tử bằng việc kết thúc rỗng.

**onError** và **onComplete** được gọi là **terminal signals**. Cả hai kết thúc Subscription hiện tại; không cần gọi **cancel()** sau khi đã nhận một terminal signal. Chúng cũng không cần đợi thêm nhu cầu **request(n)** mới được phát ra.

## 4. Backpressure và thứ tự quan sát thực tế

Sau khi nhận **onSubscribe(s)**, Subscriber biểu thị khả năng nhận bằng **s.request(n)**:

1. **request(2)** cho phép tối đa hai **onNext** bổ sung, không phải lời hứa chắc chắn sẽ nhận đủ hai phần tử.
2. Khi nhận được mỗi **onNext**, một đơn vị nhu cầu được đáp ứng. Có thể gọi tiếp **request(1)** hoặc **request(k)** để tăng nhu cầu chưa được đáp ứng.
3. Publisher không được phát **onNext** nếu tổng số phần tử đã phát vượt tổng nhu cầu đã yêu cầu. Nó vẫn có thể phát **onComplete** hoặc **onError** ngay cả khi chưa có request nào.
4. **request(0)** hoặc **request(số âm)** là không hợp lệ; Subscription phải thông báo **onError** với **IllegalArgumentException**. Dùng **Long.MAX_VALUE** thường có nghĩa là yêu cầu gần như không giới hạn.
5. **cancel()** yêu cầu nguồn *cuối cùng* dừng phát và giải phóng tài nguyên; không bảo đảm chặn ngay một số tín hiệu đang trên đường truyền và không tự sinh **onComplete**.

Ví dụ về nhu cầu nhận:

~~~text
Subscriber                         Publisher
    | -------- subscribe() ---------> |
    | <------- onSubscribe(s) ------- |
    | -------- s.request(2) --------> |
    | <--------- onNext(A) ---------- |
    | <--------- onNext(B) ---------- |
    |     (hết nhu cầu onNext)        |
    | -------- s.request(1) --------> |
    | <--------- onNext(C) ---------- |
    | <-------- onComplete() -------- |
    |   (không còn signal tiếp theo)  |
~~~

Trong ví dụ trên, nếu Publisher thất bại trước phần tử C, nó có thể gửi **onError** thay vì C và **onComplete**. Với một luồng vô hạn mà Subscriber không yêu cầu thêm, luồng có thể tiếp tục chờ, chứ không tự động hoàn tất.

## 5. Java 17+: chương trình chạy được với Flow API của JDK

Java cung cấp **java.util.concurrent.Flow** với các vai trò và callback tương ứng Reactive Streams. Ví dụ dùng **SubmissionPublisher** để minh họa hai đường đi độc lập: kết thúc thành công và kết thúc lỗi. **CountDownLatch** giữ chương trình chờ callback bất đồng bộ trước khi in kịch bản tiếp theo.

Lưu thành **SignalSequenceDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;

public class SignalSequenceDemo {
    static final class PrintSubscriber implements Flow.Subscriber<Integer> {
        private final CountDownLatch finished = new CountDownLatch(1);
        private Flow.Subscription subscription;

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            System.out.println("onSubscribe");
            subscription.request(1);
        }

        @Override
        public void onNext(Integer item) {
            System.out.println("onNext(" + item + ")");
            subscription.request(1);
        }

        @Override
        public void onError(Throwable error) {
            System.out.println(
                "onError(" + error.getClass().getSimpleName()
                + ": " + error.getMessage() + ")"
            );
            finished.countDown();
        }

        @Override
        public void onComplete() {
            System.out.println("onComplete");
            finished.countDown();
        }

        void awaitTermination() throws InterruptedException {
            finished.await();
        }
    }

    static void successfulStream() throws InterruptedException {
        System.out.println("=== Success ===");
        try (SubmissionPublisher<Integer> publisher =
                 new SubmissionPublisher<>()) {
            PrintSubscriber subscriber = new PrintSubscriber();
            publisher.subscribe(subscriber);
            publisher.submit(10);
            publisher.submit(20);
            publisher.close();
            subscriber.awaitTermination();
        }
    }

    static void failedStream() throws InterruptedException {
        System.out.println("=== Error ===");
        try (SubmissionPublisher<Integer> publisher =
                 new SubmissionPublisher<>()) {
            PrintSubscriber subscriber = new PrintSubscriber();
            publisher.subscribe(subscriber);
            publisher.closeExceptionally(
                new IllegalStateException("source failed")
            );
            subscriber.awaitTermination();
        }
    }

    public static void main(String[] args) throws InterruptedException {
        successfulStream();
        failedStream();
    }
}
~~~

Biên dịch và chạy, không cần thư viện ngoài JDK:

~~~bash
javac SignalSequenceDemo.java
java SignalSequenceDemo
~~~

Kết quả stdout của chương trình:

~~~text
=== Success ===
onSubscribe
onNext(10)
onNext(20)
onComplete
=== Error ===
onSubscribe
onError(IllegalStateException: source failed)
~~~

Đọc code theo trình tự:

- **publisher.subscribe(subscriber)** đăng ký đối tượng nhận; mỗi lần đăng ký tạo một Subscription riêng.
- **onSubscribe** lưu Subscription và yêu cầu một phần tử. Mỗi lần **onNext** xử lý xong, Subscriber yêu cầu thêm một phần tử.
- **submit(10)**, **submit(20)** đưa phần tử vào Publisher; **close()** thông báo nguồn đã hết, nên đường thành công nhận **onComplete** sau các phần tử.
- Ở đường lỗi, **closeExceptionally(...)** phát **onError** và không phát **onComplete**.
- **awaitTermination()** chỉ phục vụ việc chờ output của ví dụ: callback có thể chạy trên thread khác; bảo đảm thứ tự tín hiệu đối với một Subscriber không có nghĩa mọi callback phải chạy trên cùng thread.

Lưu ý: **Flow** là API chuẩn của JDK thể hiện cùng các khái niệm giao thức. Trong Spring WebFlux, API thường gặp là **org.reactivestreams.Publisher/Subscriber/Subscription** qua Project Reactor; không trộn trực tiếp hai bộ kiểu nếu không có bộ chuyển đổi phù hợp.

## 6. Liên hệ với Reactor và Spring WebFlux

Đoạn minh họa dưới đây dành cho dự án **đã có reactor-core**, ví dụ một ứng dụng Spring WebFlux. Đây là snippet minh họa sử dụng **Flux**, không phải tệp Java độc lập:

~~~java
Flux.just(10, 20)
    .doOnSubscribe(s -> System.out.println("onSubscribe"))
    .doOnNext(x -> System.out.println("onNext(" + x + ")"))
    .doOnError(e -> System.out.println("onError: " + e.getMessage()))
    .doOnComplete(() -> System.out.println("onComplete"))
    .subscribe();
~~~

Với nguồn **Flux.just(10, 20)**, subscriber mặc định của overload **subscribe()** yêu cầu dữ liệu và sẽ quan sát chuỗi thành công. Nếu đổi nguồn thành **Flux.error(new IllegalStateException("source failed"))**, luồng sẽ có **onError** thay cho **onComplete**; khi subscribe một luồng có thể lỗi, nên cung cấp error consumer thích hợp hoặc xử lý lỗi bằng operator như **onErrorResume**.

Cần phân biệt **vị trí quan sát**: operator **onErrorResume** bắt lỗi ở upstream rồi đăng ký fallback. Vì vậy nguồn ban đầu có thể kết thúc bằng **onError**, trong khi subscriber ở cuối pipeline nhận dữ liệu fallback và **onComplete**. Điều này không phá quy tắc "mỗi Subscription chỉ có tối đa một terminal signal"; các tín hiệu đang được quan sát ở những đoạn khác nhau của pipeline.

Ví dụ về ứng dụng: với endpoint Spring WebFlux trả về **Flux<T>**, Reactive Streams chi phối tín hiệu giữa các publisher/operator/subscriber; việc HTTP client ngắt kết nối có thể dẫn tới **cancel()**, không đồng nghĩa với **onComplete**. Xử lý giải phóng tài nguyên nên tính đến cả lỗi lẫn hủy, ví dụ bằng **doFinally(...)** hoặc cơ chế quản lý tài nguyên phù hợp.

## 7. Luật quan trọng và lỗi thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| "onSubscribe là phần tử đầu tiên" | Đây là callback thiết lập **Subscription**; dữ liệu chỉ xuất hiện trong **onNext**. |
| "request(3) chắc chắn tạo ra ba onNext" | Đây là **giới hạn tối đa được phép phát thêm**; nguồn rỗng, ít dữ liệu hoặc lỗi có thể kết thúc sớm. |
| "onComplete và onError có thể cùng xuất hiện" | Trên cùng Subscription chỉ có **một trong hai**, tối đa một lần. |
| "onError cần một onNext hoặc request trước đó" | Lỗi có thể được thông báo ngay sau **onSubscribe**, không phụ thuộc demand. |
| "cancel() sẽ gọi onComplete" | Hủy là tín hiệu điều khiển, thường **không có terminal callback** sau đó; tín hiệu đang truyền có thể còn tới. |
| "Callback chạy song song để tăng tốc" | Đối với cùng Subscriber, Publisher phải gửi tín hiệu **tuần tự, không chồng lấn**, kể cả nếu dùng nhiều thread. |
| "Có thể ném exception tùy ý trong onNext" | Subscriber cần xử lý và/hay **cancel()** theo hợp đồng; ném exception từ callback có thể phá giao thức. Lỗi của Publisher được báo bằng **onError**. |
| "Có thể gửi null qua onNext để biểu diễn rỗng" | Phần tử null không hợp lệ theo Reactive Streams; nguồn rỗng kết thúc bằng **onComplete**. |

Khi debug, hãy ghi log sự kiện theo *từng Subscription* (và theo vị trí operator nếu dùng Reactor). Kiểm tra **onSubscribe có xuất hiện trước không**, **request có cấp đủ demand không**, **terminal signal là loại nào**, và **có cancel sớm không**. Chỉ nhìn số lượng **onNext** mà bỏ qua demand/cancellation dễ dẫn tới kết luận sai.

## 8. Tự kiểm tra

1. Một Publisher vừa đăng ký Subscriber và không có phần tử nào. Thứ tự tối thiểu khi kết thúc bình thường là gì? **onSubscribe → onComplete.**
2. Sau **request(2)**, Publisher phát hai **onNext** rồi chưa kết thúc. Có được phát phần tử thứ ba ngay không? **Không**, trừ khi có thêm request từ Subscriber.
3. Sau **onError**, Subscriber có thể nhận **onComplete** trên cùng Subscription không? **Không**. Muốn khôi phục lỗi, pipeline phải xử lý bằng cơ chế recovery thích hợp, tạo chuỗi quan sát mới ở downstream.

## 9. Tài liệu tra cứu

- Reactive Streams Specification for the JVM: https://github.com/reactive-streams/reactive-streams-jvm
- JDK Flow.Subscription (Java 21): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscription.html
- JDK Flow.Subscriber (Java 21): https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/Flow.Subscriber.html