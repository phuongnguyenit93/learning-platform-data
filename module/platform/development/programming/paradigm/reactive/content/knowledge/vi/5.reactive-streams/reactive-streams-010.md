# Java Flow và cách kết nối với hệ sinh thái Reactive Streams

Từ Java 9, JDK cung cấp API `java.util.concurrent.Flow` để mô tả giao tiếp reactive giữa bên phát và bên nhận dữ liệu. API này có các khái niệm `Publisher`, `Subscriber`, `Subscription` và `Processor`, tương ứng với những thành phần trong đặc tả Reactive Streams. Nhờ sự tương đồng về hợp đồng, một ứng dụng Java có thể kết nối mã dùng Flow với thư viện dùng Reactive Streams, chẳng hạn Project Reactor.

Chủ đề này thuộc chương **Reactive Streams** của REACTIVE_PROGRAMMING. Module tập trung vào tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams; sau đó thực hành Mono, Flux, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Hiểu vị trí của Java Flow giúp ta tích hợp API chuẩn của JDK với những thư viện cung cấp khả năng xử lý luồng phong phú hơn.

## Java Flow là gì?

`java.util.concurrent.Flow` được bổ sung trong Java 9. Đây là bộ interface mô tả giao thức phát và tiêu thụ dữ liệu có backpressure. Flow cung cấp các kiểu lồng nhau sau:

| Kiểu trong Java Flow | Vai trò |
|---|---|
| `Flow.Publisher<T>` | Phát các phần tử kiểu `T` tới Subscriber đã đăng ký |
| `Flow.Subscriber<T>` | Nhận tín hiệu đăng ký, dữ liệu và kết thúc từ Publisher |
| `Flow.Subscription` | Cầu nối điều khiển giữa Subscriber và Publisher; hỗ trợ `request(n)` và `cancel()` |
| `Flow.Processor<T, R>` | Vừa là Subscriber nhận `T`, vừa là Publisher phát `R` |

Các interface này chỉ định hợp đồng giao tiếp. Chúng không cung cấp một bộ toán tử đầy đủ như `map`, `filter`, `flatMap`, `retry` hay `window`. JDK có `SubmissionPublisher<T>` làm một Publisher triển khai sẵn, nhưng ứng dụng thường kết hợp Flow với các thư viện reactive để xây dựng pipeline lớn hơn.

## Quan hệ giữa Java Flow và Reactive Streams

Reactive Streams là đặc tả và bộ interface độc lập với JDK, được sử dụng rộng rãi trong hệ sinh thái Java. Java Flow đưa các interface tương ứng vào JDK với cùng mô hình giao tiếp và ngữ nghĩa backpressure. Các cặp kiểu có vai trò tương ứng như sau:

| Java Flow (`java.util.concurrent`) | Reactive Streams (`org.reactivestreams`) |
|---|---|
| `Flow.Publisher<T>` | `Publisher<T>` |
| `Flow.Subscriber<T>` | `Subscriber<T>` |
| `Flow.Subscription` | `Subscription` |
| `Flow.Processor<T, R>` | `Processor<T, R>` |

Hai nhóm interface có hình dạng và quy tắc tương ứng, nhưng chúng thuộc hai package và là hai kiểu Java riêng biệt. Một `Flow.Publisher<T>` không tự động được xem là `org.reactivestreams.Publisher<T>`. Vì thế, không thể luôn truyền trực tiếp một đối tượng Flow vào `Flux.from(...)`, bởi `Flux.from` nhận Publisher của Reactive Streams. Cần dùng adapter để chuyển giao thức ở ranh giới.

Sự khác biệt này chủ yếu nằm ở kiểu API mà thư viện công bố. Các khái niệm quan trọng vẫn giống nhau: Subscriber nhận `onSubscribe`, phát `request(n)`, nhận `onNext`, và cuối cùng có thể nhận `onComplete` hoặc `onError`. Subscriber có thể hủy bằng `cancel`. Việc chuyển từ Flow sang Reactive Streams không làm mất ý nghĩa của demand, hủy hay terminal signal nếu adapter được triển khai đúng.

## Hợp đồng tín hiệu trong Java Flow

Một Subscriber tự triển khai cần hiểu rõ vòng đời đăng ký:

1. Publisher gọi `onSubscribe(subscription)` để cung cấp Subscription.
2. Subscriber gọi `subscription.request(n)` để yêu cầu dữ liệu. Không có nhu cầu mặc định nếu Subscriber chưa yêu cầu.
3. Publisher phát tối đa số phần tử đã được yêu cầu qua `onNext(item)`.
4. Publisher kết thúc bằng `onComplete()` khi hoàn tất bình thường hoặc `onError(error)` khi thất bại.
5. Subscriber có thể gọi `cancel()` để yêu cầu ngừng nhận thêm dữ liệu.

Các tín hiệu của một subscription phải được tuần tự hóa. Publisher không được gọi `onNext` trước `onSubscribe`, phát `null`, phát vượt demand, hoặc tiếp tục phát dữ liệu sau terminal signal. Nếu Subscriber gọi `request(n)` với `n` không dương, Publisher tuân thủ hợp đồng phải báo lỗi theo quy tắc của Flow. Hủy là yêu cầu từ Subscriber; không nên chờ `onComplete` như một xác nhận cho thao tác `cancel`.

Subscriber nên sẵn sàng nhận tín hiệu ngay sau khi xử lý `onSubscribe`, vì Publisher có thể phát đồng bộ khi demand được yêu cầu. Cách an toàn phổ biến là lưu Subscription rồi gọi `request` trong `onSubscribe`:

```java
import java.util.concurrent.Flow;

class LoggingSubscriber<T> implements Flow.Subscriber<T> {
    private Flow.Subscription subscription;

    @Override
    public void onSubscribe(Flow.Subscription subscription) {
        this.subscription = subscription;
        subscription.request(1);
    }

    @Override
    public void onNext(T item) {
        System.out.println("Received: " + item);
        subscription.request(1);
    }

    @Override
    public void onError(Throwable error) {
        System.err.println("Stream failed: " + error.getMessage());
    }

    @Override
    public void onComplete() {
        System.out.println("Stream completed");
    }
}
```

Subscriber trên yêu cầu một phần tử lúc bắt đầu và yêu cầu thêm một phần tử sau khi xử lý mỗi phần tử. Đây là cách tiêu thụ từng phần tử theo nhu cầu. Trong ứng dụng thực tế, cần cân nhắc thời điểm gọi `request` để phản ánh năng lực xử lý; nếu xử lý bất đồng bộ, không nên yêu cầu vô hạn phần tử rồi đưa tất cả vào một hàng đợi không giới hạn.

## `SubmissionPublisher`: Publisher có sẵn trong JDK

`SubmissionPublisher<T>` là triển khai `Flow.Publisher<T>` trong JDK. Nó hỗ trợ phát dữ liệu bất đồng bộ bằng một `Executor`, quản lý bộ đệm riêng cho từng Subscriber và tôn trọng demand khi chuyển các phần tử tới Subscriber. Constructor mặc định dùng common ForkJoinPool và dung lượng bộ đệm mặc định; ứng dụng có thể chỉ định executor và giới hạn bộ đệm khi tạo publisher.

Ví dụ dưới đây phát ba sự kiện đơn hàng. Subscriber yêu cầu một phần tử mỗi lần nhận và thông báo khi luồng hoàn tất:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;

public class FlowSubmissionExample {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch finished = new CountDownLatch(1);

        try (SubmissionPublisher<String> publisher =
                 new SubmissionPublisher<>()) {
            publisher.subscribe(new Flow.Subscriber<>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription subscription) {
                    this.subscription = subscription;
                    subscription.request(1);
                }

                @Override
                public void onNext(String event) {
                    System.out.println("Event: " + event);
                    subscription.request(1);
                }

                @Override
                public void onError(Throwable error) {
                    error.printStackTrace();
                    finished.countDown();
                }

                @Override
                public void onComplete() {
                    System.out.println("All events delivered");
                    finished.countDown();
                }
            });

            publisher.submit("ORDER_CREATED");
            publisher.submit("PAYMENT_CONFIRMED");
            publisher.submit("ORDER_SHIPPED");
        }

        finished.await();
    }
}
```

`submit` đưa phần tử vào publisher để phân phối tới các Subscriber. Việc gọi `close()` thông qua try-with-resources báo rằng nguồn đã kết thúc; các phần tử đã được xếp trước đó được xử lý trước tín hiệu hoàn tất. `CountDownLatch` giữ luồng main cho đến khi Subscriber nhận terminal signal, vì quá trình giao nhận của `SubmissionPublisher` là bất đồng bộ.

`SubmissionPublisher` có bộ đệm hữu hạn cho mỗi Subscriber. Khi một Subscriber chậm hoặc không yêu cầu dữ liệu, bộ đệm của Subscriber đó có thể đầy. `submit` có thể chờ khi không còn chỗ để tiếp nhận; `offer` cung cấp cách thử phát với timeout và hàm xử lý khi không thể tiếp nhận. Nếu chọn chiến lược bỏ phần tử, ứng dụng phải xác định rõ dữ liệu nào được phép bỏ và theo dõi số lần bỏ. Không nên tăng buffer vô hạn để che giấu việc consumer không theo kịp.

Các phương thức `close()` và `closeExceptionally(error)` lần lượt kết thúc publisher bình thường hoặc kết thúc do lỗi. Sau khi publisher đóng, không thể tiếp tục submit dữ liệu mới. Cần quản lý vòng đời publisher cùng vòng đời executor và thành phần đăng ký để tránh giữ tài nguyên lâu hơn cần thiết.

## Kết nối Flow với Project Reactor

Project Reactor sử dụng các interface Reactive Streams trong API của `Flux` và `Mono`. Khi một thư viện JDK cung cấp `Flow.Publisher`, Reactor có `JdkFlowAdapter` để chuyển đổi giữa hai kiểu Publisher. Adapter nằm trong package `reactor.adapter` của Reactor Core.

### Chuyển `Flow.Publisher` thành `Flux`

```java
import java.util.concurrent.Flow;
import reactor.adapter.JdkFlowAdapter;
import reactor.core.publisher.Flux;

Flow.Publisher<String> jdkPublisher = obtainFlowPublisher();

Flux<String> events = JdkFlowAdapter.flowPublisherToFlux(jdkPublisher);

events
    .filter(event -> event.startsWith("ORDER_"))
    .map(String::toLowerCase)
    .subscribe(System.out::println);
```

`flowPublisherToFlux` bọc Flow Publisher thành `Flux` để tiếp tục sử dụng các toán tử Reactor. Subscriber của Reactor được adapter chuyển thành Subscriber tương ứng của Flow. Demand và cancel được chuyển tiếp qua ranh giới adapter theo hợp đồng.

### Chuyển `Publisher` của Reactor thành `Flow.Publisher`

Khi một API bên ngoài yêu cầu kiểu `Flow.Publisher`, có thể chuyển một pipeline Reactor sang Flow:

```java
import java.util.concurrent.Flow;
import reactor.adapter.JdkFlowAdapter;
import reactor.core.publisher.Flux;

Flux<Integer> pipeline = Flux.just(10, 20, 30)
    .map(value -> value + 1);

Flow.Publisher<Integer> flowPublisher =
    JdkFlowAdapter.publisherToFlowPublisher(pipeline);
```

`flowPublisher` có thể được truyền cho thành phần chỉ hiểu Java Flow. Phần xử lý vẫn được mô tả bằng pipeline Reactor; adapter chỉ chuyển đổi giao diện giao tiếp. Việc chuyển đổi không tự thêm scheduler, không biến một nguồn đồng bộ thành bất đồng bộ, và cũng không tự tạo song song. Hành vi thực thi vẫn phụ thuộc Publisher và các toán tử trong pipeline.

Nếu dự án dùng một thư viện khác trong hệ sinh thái Reactive Streams, hãy ưu tiên adapter chính thức của thư viện đó hoặc adapter tương thích Flow được cung cấp bởi Reactive Streams. Tránh tự viết lớp bọc chỉ chuyển từng callback nếu chưa xử lý đầy đủ demand, cancel, terminal signal và tuần tự hóa.

## Kết nối Flow với các thành phần Java khác

Java Flow phù hợp khi cần một hợp đồng reactive ở tầng JDK mà không muốn API công khai phụ thuộc trực tiếp vào một framework cụ thể. Một thư viện có thể nhận `Flow.Publisher<T>` để tiêu thụ sự kiện; ứng dụng triển khai nguồn bằng `SubmissionPublisher` hoặc chuyển một pipeline Reactor sang Flow tại ranh giới.

Ví dụ, một thành phần nghiệp vụ có thể cung cấp API Flow:

```java
import java.util.concurrent.Flow;

public interface OrderEventSource {
    Flow.Publisher<OrderEvent> events();
}
```

Việc dùng interface của JDK giúp chữ ký API không phụ thuộc `Flux` hay `Mono`. Ở tầng triển khai, ứng dụng vẫn có thể sử dụng Reactor để kết hợp dữ liệu, xử lý retry, timeout, scheduler và kiểm thử. Khi tích hợp, cần thống nhất ai sở hữu vòng đời Publisher, ai chịu trách nhiệm đóng nguồn và cách lỗi được truyền qua ranh giới.

Java Flow cũng có thể được kết hợp với `CompletableFuture`. Tuy nhiên, `CompletableFuture` thường biểu diễn một kết quả bất đồng bộ đơn lẻ, còn Flow biểu diễn một chuỗi có thể có nhiều phần tử và demand. Chuyển một `CompletionStage<T>` thành `Mono<T>` thường hợp với kết quả đơn; chuyển một nguồn sự kiện thành `Flow.Publisher<T>` phù hợp khi cần nhiều phần tử theo thời gian. Chọn kiểu theo ngữ nghĩa dữ liệu giúp API dễ hiểu hơn.

## Khi nào nên dùng Flow, khi nào nên dùng Reactor?

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Cần một hợp đồng Publisher/Subscriber chuẩn có sẵn trong JDK | Java Flow |
| Cần một Publisher bất đồng bộ đơn giản trong ứng dụng JDK | `SubmissionPublisher` |
| Cần `map`, `filter`, `flatMap`, kết hợp nhiều nguồn, retry và timeout | Reactor `Flux`/`Mono` hoặc thư viện reactive tương ứng |
| Cần tích hợp thư viện JDK dùng Flow với hệ thống Reactor | `JdkFlowAdapter` |
| Cần API công khai không phụ thuộc framework nhưng triển khai nội bộ bằng Reactor | Công bố `Flow.Publisher` và chuyển đổi ở ranh giới |
| Cần kiểm soát scheduler, context và kiểm thử pipeline phong phú | Reactor và các công cụ kiểm thử tương ứng |

Flow không cạnh tranh với Reactor ở cùng một tầng trừu tượng. Flow chuẩn hóa giao thức ở cấp JDK; Reactor cung cấp mô hình lập trình và bộ công cụ để xây dựng pipeline trên giao thức Reactive Streams. Dùng Flow ở ranh giới liên thư viện và dùng Reactor cho phần xử lý phức tạp là một cách kết hợp phổ biến.

## Những điểm cần chú ý khi tích hợp

**Không nhầm tương đương ngữ nghĩa với tương thích kiểu.** Hai nhóm interface có cùng vai trò nhưng không thể truyền trực tiếp thay thế nhau trong chữ ký Java. Luôn chuyển đổi bằng adapter tương thích.

**Không giả định adapter tạo bất đồng bộ.** Chuyển một `Flow.Publisher` đồng bộ sang `Flux` không tự chuyển việc phát tín hiệu sang thread khác. Nếu cần đổi nơi thực thi, hãy dùng scheduler phù hợp trong Reactor sau khi chuyển đổi.

**Giữ nguyên backpressure qua ranh giới.** Adapter phải chuyển tiếp `request(n)` và `cancel`. Nếu nguồn gốc là push-only, cần một chính sách buffer hoặc overflow rõ ràng; adapter không thể ép thiết bị bên ngoài ngừng phát nếu API nguồn không hỗ trợ demand.

**Quản lý buffer và executor.** Với `SubmissionPublisher`, bộ đệm đầy có thể khiến `submit` chờ. Hãy chọn kích thước buffer, executor và chính sách `offer` theo tải thực tế. Tránh dùng common pool cho tác vụ blocking kéo dài.

**Quản lý terminal signal và lỗi.** Lỗi từ nguồn Flow phải đi qua `onError`; lỗi xảy ra trong pipeline Reactor được chuyển thành terminal signal khi xuất ra Flow. Không phát lỗi như một phần tử dữ liệu trừ khi domain model chủ ý biểu diễn lỗi bằng kiểu dữ liệu riêng.

**Quản lý vòng đời.** Hủy subscription downstream phải truyền tới nguồn. Khi dùng `SubmissionPublisher`, đóng publisher khi nguồn không còn phát và đảm bảo subscriber có cơ hội xử lý terminal signal nếu ứng dụng cần đợi hoàn tất.

**Kiểm tra phiên bản Java.** `java.util.concurrent.Flow` và `SubmissionPublisher` có từ Java 9. Dự án chạy trên Java 8 cần dùng các interface Reactive Streams từ dependency bên ngoài hoặc nâng phiên bản runtime trước khi sử dụng API Flow của JDK.

## Kiểm thử tương tác Flow và Reactor

Khi kiểm thử adapter, cần xác nhận cả dữ liệu lẫn giao thức: phần tử được chuyển đúng thứ tự, demand được truyền, cancel dừng nguồn và terminal signal được chuyển đúng loại. Với pipeline Reactor, `StepVerifier` kiểm tra kết quả ở phía `Flux`/`Mono`; với Publisher Flow, có thể viết Subscriber kiểm thử ghi nhận các callback và dùng latch để chờ tín hiệu bất đồng bộ.

Một ví dụ kiểm tra phần chuyển đổi từ Flow sang Flux:

```java
import java.util.concurrent.Flow;
import reactor.adapter.JdkFlowAdapter;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

Flow.Publisher<Integer> flowSource = obtainFlowPublisher();
Flux<Integer> adapted = JdkFlowAdapter.flowPublisherToFlux(flowSource);

StepVerifier.create(adapted)
    .expectNext(1, 2, 3)
    .verifyComplete();
```

`obtainFlowPublisher()` đại diện cho nguồn Flow được tạo trong test, chẳng hạn `SubmissionPublisher` hoặc Publisher giả lập. Trong kiểm thử nguồn bất đồng bộ, cần điều khiển thời điểm phát và đóng nguồn một cách xác định; không dùng `Thread.sleep` để đoán rằng callback đã chạy xong. Dùng latch, scheduler ảo khi phù hợp hoặc công cụ test publisher để đồng bộ kỳ vọng.

Một test adapter tốt nên có thêm tình huống Subscriber hủy sau một số phần tử và xác nhận nguồn dừng, cũng như tình huống nguồn kết thúc bằng lỗi để xác nhận lỗi không bị biến thành `onComplete`. Với `SubmissionPublisher`, có thể kiểm thử trường hợp consumer chậm để xác nhận chính sách buffer/offer mà ứng dụng lựa chọn.

## Tự kiểm tra

1. Java Flow được bổ sung từ phiên bản Java nào và bốn interface cốt lõi của nó có vai trò gì?
2. Vì sao `Flow.Publisher<T>` không thể truyền trực tiếp vào `Flux.from(...)` dù hai API có hợp đồng tương ứng?
3. Subscriber Flow cần gọi phương thức nào để bắt đầu nhận dữ liệu và để yêu cầu thêm phần tử sau mỗi lần xử lý?
4. `SubmissionPublisher` xử lý việc phát bất đồng bộ và bộ đệm theo từng Subscriber như thế nào? Điều gì có thể xảy ra khi một Subscriber chậm?
5. Adapter `JdkFlowAdapter` có tự tạo scheduler mới hoặc làm nguồn đồng bộ trở thành bất đồng bộ không? Giải thích.
6. Khi chuyển một `Flux` thành `Flow.Publisher`, vì sao vẫn phải kiểm thử demand, cancel và terminal signal ở ranh giới tích hợp?

Khi nắm được quan hệ giữa Java Flow và Reactive Streams, bạn có thể dùng API chuẩn của JDK ở ranh giới tích hợp, chuyển đổi sang `Flux`/`Mono` để xây dựng pipeline, và giữ đúng hợp đồng demand, tín hiệu kết thúc cùng vòng đời subscription trong toàn hệ thống.
