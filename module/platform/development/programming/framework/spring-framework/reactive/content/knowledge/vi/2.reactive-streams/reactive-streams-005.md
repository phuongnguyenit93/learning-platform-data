# Tuần tự tín hiệu trong một subscription (Reactive Streams)

## 1. Mục tiêu và phạm vi

Khi một `Publisher` kết nối với một `Subscriber`, hai bên trao đổi dữ liệu qua một `Subscription` cụ thể. “Tuần tự tín hiệu” (*serial signaling*) là hợp đồng về **thứ tự và tính không đồng thời của các callback mà Publisher gửi tới Subscriber trong subscription đó**, kể cả khi hệ thống có nhiều luồng xử lý.

Sau bài này, bạn cần phân biệt được: (1) chuỗi tín hiệu hợp lệ; (2) vì sao nhiều thread vẫn có thể tham gia nhưng không được cùng lúc phát callback xuống một Subscriber; (3) quan hệ giữa serial signaling, backpressure, hủy đăng ký và thứ tự phần tử; (4) cách quan sát hoặc sửa lỗi trong Spring WebFlux/Project Reactor.

Bốn callback theo chiều dữ liệu là `onSubscribe(Subscription)`, `onNext(T)`, `onError(Throwable)` và `onComplete()`. `request(n)` và `cancel()` là thao tác điều khiển theo chiều ngược lại (Subscriber → Subscription); chúng ảnh hưởng vòng đời nhưng **không được đếm thành `onNext` hoặc tín hiệu kết thúc**.

## 2. Giao thức tín hiệu hợp lệ

Quy tắc tổng quát của Reactive Streams:

~~~text
onSubscribe → onNext* → (onError | onComplete)?
~~~

Ký hiệu `*` nghĩa là không, một hoặc nhiều lần; `?` nghĩa là tín hiệu kết thúc có thể chưa xuất hiện (luồng còn sống, bị hủy, hoặc chưa hoàn thành). Một subscription đang hoạt động nhận `onSubscribe` trước mọi callback dữ liệu; mỗi `onNext` mang đúng một phần tử; nếu luồng kết thúc tự nhiên thì phát `onComplete`, nếu thất bại thì phát `onError`. Hai loại kết thúc loại trừ nhau và **không callback nào được phát sau tín hiệu kết thúc**.

Ví dụ đúng:

~~~text
onSubscribe → onComplete                              (luồng rỗng)
onSubscribe → onNext(A) → onNext(B) → onComplete        (thành công)
onSubscribe → onNext(A) → onError(cause)               (thất bại)
onSubscribe → onNext(A) → ...                          (luồng còn mở)
onSubscribe → onNext(A) → [Subscriber gọi cancel]      (có thể không có terminal)
~~~

Ví dụ sai và lý do:

| Chuỗi hoặc tình huống | Vi phạm |
| --- | --- |
| `onNext(A) → onSubscribe` | Dữ liệu xuất hiện trước khi có subscription. |
| `onSubscribe → onComplete → onNext(A)` | Phát dữ liệu sau khi đã hoàn thành. |
| `onSubscribe → onError(e) → onComplete` | Hai terminal cho cùng subscription. |
| `onSubscribe → onNext(A) → onComplete → onComplete` | Terminal bị lặp. |
| Thread 1 đang gửi `onNext(A)`, Thread 2 đồng thời gửi `onNext(B)` vào cùng Subscriber | Các callback không được serialize. |

Một subscription có **tối đa một tín hiệu terminal**. Nếu bị `cancel()`, nhà phát phải *cuối cùng* ngừng gửi tín hiệu; không được giả định việc hủy tức thì loại bỏ tất cả callback đã ở trong hàng đợi hoặc đang truyền. Với luồng chạy liên tục, việc chưa nhận terminal tự nó không phải lỗi.

## 3. “Tuần tự” chính xác là gì?

Reactive Streams quy tắc **Publisher 1.3** yêu cầu `onSubscribe`, `onNext`, `onError` và `onComplete` được signal *serially*. Trên JVM, điều này nghĩa là có quan hệ **happens-before** thích hợp giữa những lần gọi và không để hai thread đồng thời xâm nhập các callback cho **cùng một subscription**. `happens-before` bảo đảm cả thứ tự quan sát lẫn việc công bố thay đổi bộ nhớ giữa các giai đoạn.

~~~text
Hợp lệ:  Thread A: onNext(1) ── kết thúc/bàn giao ──► Thread B: onNext(2)
Sai:     Thread A: onNext(1) ───────────────┐
         Thread B:       onNext(2) ─────────┘   (chồng lấn)
~~~

Không có yêu cầu mọi callback phải chạy trên **cùng một thread**. Một Publisher có thể chuyển từ thread A sang thread B bằng hàng đợi, khóa hoặc cơ chế nguyên tử, miễn duy trì thứ tự/happens-before. Việc `request(1)` ở bên trong `onSubscribe`/`onNext` đôi khi kích hoạt nguồn đồng bộ; vì thế Subscriber phải viết an toàn với callback được kích hoạt trong ngữ cảnh của `request`, và Subscription phải hạn chế đệ quy gây tràn stack. Không nên suy luận rằng một callback luôn ở thread khác hoặc rằng gọi `request` luôn chờ bất đồng bộ.

**Phạm vi là từng subscription.** Hai Subscriber khác nhau hoặc hai nhánh độc lập có thể cùng hoạt động; hợp đồng không bắt toàn bộ ứng dụng chạy một thread. Khi nhiều nguồn được hợp nhất, dữ liệu có thể đan xen theo thời điểm đến, nhưng callback gửi đến **một downstream Subscriber** vẫn phải tuần tự.

Cũng cần phân biệt:

- **Tuần tự callback:** không có hai lời gọi `onNext`/terminal tới cùng Subscriber đang diễn ra đồng thời.
- **Giữ nguyên thứ tự dữ liệu đầu vào:** ví dụ A trước B vẫn luôn phát ra A trước B sau xử lý. Đây là tính chất riêng của nguồn/toán tử; `flatMap` có thể đổi thứ tự vì các inner publisher hoàn thành khác nhau.
- **Xử lý đồng bộ:** tất cả hoạt động trên một thread, không nhất thiết là yêu cầu của Reactive Streams.

## 4. Backpressure, request và cancel trong cùng subscription

Sau `onSubscribe(subscription)`, Subscriber gọi `subscription.request(n)` với `n > 0` để cấp nhu cầu (*demand*). Tổng số `onNext` phát ra **không bao giờ được vượt quá tổng nhu cầu đã nhận** (Publisher 1.1). Nhu cầu cộng dồn: `request(2)` rồi `request(1)` cho phép tối đa ba phần tử, trừ phần đã phát. Publisher được phép phát **ít hơn** mức đã yêu cầu rồi kết thúc. `onComplete` hoặc `onError` có thể tới dù chưa gọi `request` (ví dụ nguồn rỗng hoặc thất bại ngay).

~~~text
Subscriber                     Publisher
   |                              |
   |<---- onSubscribe(s) ---------|
   |---- s.request(2) ----------->|
   |<---- onNext(A) --------------|
   |<---- onNext(B) --------------|
   |      (không được phát C khi  |
   |       chưa có thêm demand)   |
   |---- s.request(1) ----------->|
   |<---- onNext(C) --------------|
   |<---- onComplete() -----------|
~~~

Theo Subscription 3.9, `request(0)` hoặc số âm khi subscription chưa bị hủy là yêu cầu không hợp lệ: Subscription phải báo `onError(IllegalArgumentException)` theo hợp đồng, không được âm thầm coi như yêu cầu “0 dữ liệu”. `request`/`cancel` là các thao tác của Subscriber; khi gọi chúng từ nhiều thread, Subscriber phải bảo đảm việc gọi được đồng bộ hóa theo quy tắc 2.7. Khi đã terminal, coi subscription như bị hủy và không phát tiếp. `cancel()` yêu cầu dừng *eventually*; một `onNext` đã được lên lịch có thể còn đến trong thời gian chuyển tiếp.

Serial signaling và backpressure giải quyết hai vấn đề khác nhau: **callback không chồng lấn** và **số phần tử không vượt demand**. Thỏa điều kiện thứ nhất chưa đủ để thỏa điều kiện thứ hai, và ngược lại.

## 5. Ví dụ Java 17+ chạy độc lập: quan sát thứ tự

Java `java.util.concurrent.Flow` dùng giao thức tương đương Reactive Streams trong JDK. Ví dụ sau không cần thêm thư viện. `SubmissionPublisher` phát bất đồng bộ, còn Subscriber yêu cầu từng phần tử để người học thấy ranh giới giữa `request` và callback.

Tạo tệp `SerialSignalsDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;

public class SerialSignalsDemo {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch finished = new CountDownLatch(1);

        try (SubmissionPublisher<Integer> publisher = new SubmissionPublisher<>()) {
            publisher.subscribe(new Flow.Subscriber<>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription s) {
                    subscription = s;
                    System.out.println("onSubscribe");
                    s.request(1);
                }

                @Override
                public void onNext(Integer value) {
                    System.out.println("onNext(" + value + ")");
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable error) {
                    System.out.println("onError: " + error.getMessage());
                    finished.countDown();
                }

                @Override
                public void onComplete() {
                    System.out.println("onComplete");
                    finished.countDown();
                }
            });

            publisher.submit(10);
            publisher.submit(20);
            publisher.submit(30);
        } // close() yêu cầu phát terminal sau các phần tử đang chờ
        finished.await(); // đợi callback kết thúc trước khi thoát main
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên:

~~~bash
javac --release 17 SerialSignalsDemo.java
java SerialSignalsDemo
~~~

Kết quả stdout của luồng chạy thành công:

~~~text
onSubscribe
onNext(10)
onNext(20)
onNext(30)
onComplete
~~~

`SubmissionPublisher` có thể chạy callback trên thread nền, nhưng đối với một Subscriber thứ tự trên vẫn đúng. Không dùng thứ tự in ra giữa **nhiều Subscriber** để suy luận có một lịch trình toàn cục. `CountDownLatch` chỉ để hàm `main` không thoát trước lúc callback terminal hoàn tất.

## 6. Áp dụng trong Spring WebFlux với Project Reactor

Spring WebFlux thường dùng `Flux<T>` và `Mono<T>` của Reactor. Chúng tuân thủ hợp đồng Publisher/Subscriber Reactive Streams; `Mono` có tối đa một `onNext`, `Flux` có thể có nhiều. Trong dự án đã có `spring-boot-starter-webflux`, chạy lớp sau qua IDE hoặc cấu hình chạy Java tương ứng:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class ReactorSerialSignalsDemo {
    public static void main(String[] args) {
        Flux.just("A", "B").subscribe(new BaseSubscriber<String>() {
            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                System.out.println("onSubscribe");
                request(1);
            }

            @Override
            protected void hookOnNext(String value) {
                System.out.println("onNext(" + value + ")");
                request(1);
            }

            @Override
            protected void hookOnComplete() {
                System.out.println("onComplete");
            }

            @Override
            protected void hookOnError(Throwable error) {
                System.out.println("onError: " + error.getMessage());
            }
        });
    }
}
~~~

Stdout với nguồn `Flux.just` thành công:

~~~text
onSubscribe
onNext(A)
onNext(B)
onComplete
~~~

Ở đây `BaseSubscriber` đưa `onSubscribe`/`onNext`/terminal vào các hook tương ứng; `request(1)` cho phép nhận một phần tử mỗi lượt. Reactor xử lý việc phát tuần tự cho nguồn `Flux.just`. Đoạn này là **chương trình Reactor có phụ thuộc thư viện**; ví dụ JDK ở mục 5 mới là chương trình chạy chỉ với `javac`/`java` chuẩn.

Trong một pipeline như `Flux.just(...).publishOn(scheduler).map(...).subscribe(...)`, `publishOn` có thể đổi thread xử lý downstream nhưng không cho phép hai tín hiệu downstream chồng lấn. `flatMap` cho các nguồn con hoạt động đồng thời và có thể **đan xen/reorder** phần tử; nếu nghiệp vụ cần giữ thứ tự của nguồn ban đầu, cân nhắc `concatMap` (xử lý inner tuần tự) hoặc `flatMapSequential` (cho inner chạy đồng thời nhưng giữ thứ tự khi phát). Không nhầm yêu cầu giữ thứ tự nghiệp vụ với quy tắc serialize callback.

Khi nhiều thread cùng đẩy dữ liệu vào một `Sinks.Many`, tránh để chúng phát trực tiếp đồng thời mà không phối hợp. API `tryEmitNext` của Reactor có thể trả `Sinks.EmitResult.FAIL_NON_SERIALIZED` khi phát tranh chấp, hoặc `FAIL_TERMINATED` khi nguồn đã kết thúc. Thiết kế phù hợp thường là điều phối qua một hàng đợi/đầu phát duy nhất, hoặc dùng cơ chế retry/emission handler có kiểm soát của Reactor; **không bỏ qua kết quả lỗi rồi giả định phần tử đã được gửi**.

## 7. Nhận diện và gỡ lỗi vi phạm

1. **Phát `onNext` từ nhiều callback/thread vào cùng Subscriber:** có nguy cơ trùng thời điểm, trạng thái Subscriber bị race. Sửa ở nguồn bằng cách đưa các lần phát qua cơ chế tuần tự (queue + drain, lock hoặc API Reactor phù hợp); chỉ thêm `synchronized` tùy tiện ở nơi tiêu thụ có thể che lỗi và không giải quyết demand/terminal.
2. **Gửi `onNext` sau `onComplete`/`onError`:** nguồn chưa có trạng thái terminal nguyên tử hoặc các tác vụ bất đồng bộ vẫn phát muộn. Chặn tại một state machine thống nhất, dừng/loại bỏ tác vụ còn lại và báo lỗi ở đúng thời điểm.
3. **Phát nhiều hơn `request(n)`:** thứ tự callback có thể hoàn toàn đúng nhưng vẫn vi phạm backpressure. Theo dõi tổng `requested`, tổng `emitted`, queue và đường đi `request` qua các toán tử.
4. **Cho rằng `cancel()` phải chặn tức thì mọi callback:** xử lý race với tín hiệu đang bay và thực hiện cleanup idempotent; hợp đồng chỉ yêu cầu ngừng cuối cùng.
5. **Cho rằng `flatMap` phá tính tuần tự vì kết quả đảo thứ tự:** kiểm tra xem callback thực sự chạy chồng lấn hay chỉ có sự đan xen phần tử từ các inner publisher. Nếu chỉ cần trật tự dữ liệu, thay toán tử chứ không phải khóa toàn bộ Subscriber.

Để quan sát trong Reactor, có thể chèn `.log("signals")` vào `Flux` hoặc `Mono` ở vị trí cần kiểm tra: nhật ký có `onSubscribe`, `request`, `onNext`, `onComplete`/`onError` và `cancel` tùy luồng. Cũng có thể dùng `doOnSubscribe`, `doOnNext`, `doOnError`, `doOnComplete` và `doFinally`; lưu ý `doFinally` là hook lifecycle của Reactor, không phải callback thứ năm trong giao thức Reactive Streams. Các log từ nhiều subscriptions có thể đan xen, nên hãy gắn một định danh subscription khi chẩn đoán.

Khi **tự viết** một Publisher/Subscription thay vì dùng toán tử chuẩn, kiểm thử ít nhất: nguồn rỗng; nhiều `onNext` rồi complete; error trước/sau dữ liệu; `request(1)` tăng dần; `request(0)`; `cancel` trong lúc có tín hiệu đang chờ; hai nguồn phát cạnh tranh; và bảo đảm không callback sau terminal. Reactive Streams TCK hữu ích để kiểm tra tính tuân thủ giao thức.

## 8. Tự kiểm tra

- `onSubscribe → onNext(1) → onError(e)`: hợp lệ nếu đã có demand cho phần tử 1, không có callback nào sau error.
- `onSubscribe → onComplete` mà chưa `request`: **hợp lệ** đối với luồng rỗng.
- Thread A phát `onNext(1)` xong, thread B phát `onNext(2)` sau khi đã đồng bộ hóa đúng: **hợp lệ** dù khác thread.
- Thread A và B cùng lúc gọi `onNext` trên một Subscriber: **vi phạm serial signaling**, kể cả tổng demand đã đủ.
- `flatMap` trả kết quả B trước A nhưng callback tuần tự: **không vi phạm 1.3**; nếu cần A trước B, chọn toán tử giữ thứ tự.

**Điểm cần nhớ:** Mỗi subscription có một đường tín hiệu theo giao thức `onSubscribe → onNext* → (onError | onComplete)?`. Publisher phải phát các callback này tuần tự, tôn trọng demand và dừng sau terminal. Concurrency của nguồn hoặc việc chuyển thread không loại bỏ nghĩa vụ đó.

## Tài liệu tham khảo

- [Reactive Streams for the JVM — API protocol và quy tắc Publisher 1.1–1.8, Subscriber 2.7–2.10, Subscription 3.9](https://github.com/reactive-streams/reactive-streams-jvm#readme).
- [Project Reactor — `Flux` Javadoc, `flatMap` / `concatMap` / `flatMapSequential`](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- [Project Reactor — `Sinks.EmitResult` và các trạng thái tranh chấp/terminal](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Sinks.EmitResult.html).
