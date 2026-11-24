# Consumer<Flux<T>> và trách nhiệm đăng ký nhận dữ liệu

## 1. Bài toán: Consumer nhận Flux nhưng không xử lý phần tử nào

Trong **Spring Cloud Function**, `Supplier` tạo dữ liệu, `Function` biến đổi dữ liệu và `Consumer` nhận dữ liệu để thực hiện tác dụng phụ như ghi nhật ký, lưu đơn hàng hoặc cập nhật hệ thống bên ngoài. Các hàm có thể được tra cứu qua `FunctionCatalog`, composition và dùng cùng logic nghiệp vụ thông qua HTTP, message broker hoặc môi trường serverless.

Ở chương **Luồng phản ứng**, một consumer có thể nhận `Flux<T>` thay vì chỉ nhận một `T`:

~~~java
Consumer<Flux<String>> audit = events ->
    events.doOnNext(event -> System.out.println(event));
~~~

Đoạn này có vấn đề. `doOnNext` tạo **một publisher mới** có thêm thao tác quan sát, nhưng chưa ai subscribe vào publisher đó. Vì `Consumer.accept` trả về `void`, publisher vừa tạo cũng bị bỏ đi. Với nguồn Reactor cold, thao tác in sẽ không chạy.

Có người thử “sửa” bằng cách:

~~~java
Consumer<Flux<String>> audit = events ->
    events.doOnNext(System.out::println).subscribe();
~~~

Cách thứ hai **thật sự đăng ký nhận dữ liệu**. Tuy nhiên, nó mở ra các câu hỏi: ai xử lý `onError`, ai hủy subscription khi đóng ứng dụng, ai biết quá trình ghi dữ liệu đã hoàn tất, và message broker xác nhận thông điệp vào thời điểm nào?

**Đây là trọng tâm của bài:** Khi chọn `Consumer<Flux<T>>`, cần hiểu chính xác ai sở hữu subscription và hậu quả của kiểu trả về `void`. Trong nhiều trường hợp, `Function<Flux<T>, Mono<Void>>` diễn đạt hợp đồng bất đồng bộ tốt hơn.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `Consumer<T>` với `Consumer<Flux<T>>` và số lần gọi `accept`.
2. Giải thích vì sao `subscribe()` cần thiết khi tự viết reactive consumer trả `void`.
3. Phân biệt **tạo pipeline**, **đăng ký subscription**, **xử lý `onNext`**, **hoàn tất** và **hủy**.
4. Nhận diện lỗi từ việc tự subscribe rồi làm mất khả năng quan sát kết quả hoặc vòng đời.
5. Viết consumer có xử lý lỗi, đồng thời biết khi nào nên trả `Mono<Void>`.
6. Kiểm thử hành vi Reactor và xác minh ranh giới trách nhiệm với các adapter Spring Cloud Function.

## 2. Hợp đồng của Java Consumer không thay đổi trong môi trường reactive

Java định nghĩa:

~~~java
@FunctionalInterface
public interface Consumer<T> {
    void accept(T value);
}
~~~

`Consumer` chỉ nói rằng caller đưa cho consumer **một đối số**, và `accept` **không trả kết quả**. Nếu đối số là một publisher, `accept` vẫn chỉ là lời gọi Java đồng bộ nhận **một `Flux<T>`**; nó không tự trở thành subscriber.

| Chữ ký | Đối số của một lần gọi | Kết quả trả về từ `accept` | Cách chạy phần tử |
| --- | --- | --- | --- |
| `Consumer<OrderEvent>` | Một `OrderEvent` | `void` | Logic trong `accept` chạy với order được truyền vào |
| `Consumer<Mono<OrderEvent>>` | Một publisher phát 0–1 order | `void` | Cần subscription để nhận order |
| `Consumer<Flux<OrderEvent>>` | Một publisher phát 0–N order | `void` | Cần subscription để nhận các `onNext` |
| `Function<Flux<OrderEvent>, Mono<Void>>` | Một publisher phát 0–N order | Publisher mô tả hoàn tất/lỗi | Bên gọi có thể subscribe và quan sát kết quả |

**`Mono<Void>` không phát giá trị `Void`.** Nó biểu diễn thao tác hoàn tất thành công hoặc kết thúc bằng lỗi. Đây là lý do một `Function` trả `Mono<Void>` thường thích hợp cho “consumer bất đồng bộ cần báo đã xong”.

### 2.1. Ba sự kiện khác nhau

Giả sử có nguồn:

~~~java
Flux<String> source = Flux.just("A", "B", "C");
~~~

Thứ tự logic là:

~~~mermaid
sequenceDiagram
    participant Adapter as Caller / adapter
    participant Consumer as Consumer<Flux<T>>
    participant Pipeline as Reactor pipeline
    participant Source as Flux nguồn

    Adapter->>Consumer: accept(source)
    Consumer->>Pipeline: Tạo chuỗi toán tử
    Note over Consumer,Pipeline: Chưa có subscribe = chưa xử lý cold source
    Consumer-->>Adapter: void
    Consumer->>Pipeline: subscribe() nếu consumer tự quản lý
    Pipeline->>Source: onSubscribe + request(n)
    Source-->>Pipeline: onNext(A), onNext(B), onNext(C)
    Source-->>Pipeline: onComplete
~~~

Điểm đáng chú ý là `accept` có thể trả về trước khi dữ liệu bất đồng bộ được xử lý. Nếu không có subscription, nguồn cold có thể không bao giờ chạy.

**Một lời gọi `accept(flux)` không tương đương một lần xử lý mỗi `T`.** Framework có thể truyền một stream dài hạn vào consumer reactive; callback bên trong pipeline mới chạy cho từng phần tử.

## 3. Vì sao Spring không tự subscribe cho Consumer<Flux<T>>?

Tài liệu Spring Cloud Function và Spring Cloud Stream nêu rõ trường hợp reactive `Consumer` là đặc biệt: do trả về `void`, framework **không có tham chiếu tới publisher kết quả** để subscribe và theo dõi hoàn tất. Nếu viết `Consumer<Flux<?>>` tường minh, lập trình viên cần subscribe vào input Flux.

Điều này khác với `Function<Flux<T>, Flux<R>>`:

~~~java
Function<Flux<String>, Flux<String>> normalize =
    input -> input.map(String::trim);
~~~

Caller nhận `Flux<String>` từ `apply`, vì thế có thể quyết định subscription, demand, hủy và xử lý `onError`. Còn với:

~~~java
Consumer<Flux<String>> audit =
    input -> input.doOnNext(System.out::println);
~~~

Caller chỉ biết `accept` đã trả `void`. Pipeline mà consumer tạo không được chuyển ra ngoài để framework quản lý. Không có hợp đồng tự động “tìm publisher bên trong lambda”.

### 3.1. Phân biệt “framework gửi Flux” và “framework subscribe Flux”

Trong một tích hợp sự kiện hỗ trợ reactive function, framework có thể xây dựng nguồn `Flux<Message<T>>` và truyền nó vào `Consumer<Flux<Message<T>>>`. Việc framework **tạo và truyền publisher** không có nghĩa code trong consumer đã **subscribe** publisher đó.

Nếu consumer chỉ viết `map`, `filter` hoặc `doOnNext` rồi bỏ kết quả, các toán tử thường không chạy. Nếu consumer gọi `subscribe()`, nó chính là thành phần thực hiện đăng ký và từ thời điểm đó phải có chiến lược quan sát, lỗi, hủy cùng tài nguyên.

Các chi tiết cụ thể của việc gọi, binder và acknowledgment phụ thuộc phiên bản adapter; không được suy từ kiểu Java rằng broker sẽ tự biết thời điểm tác dụng phụ đã hoàn tất.

## 4. Từ ví dụ sai đến ví dụ đúng

### 4.1. Sai: tạo publisher nhưng không subscribe

~~~java
@Bean
Consumer<Flux<String>> silentConsumer() {
    return incoming -> incoming
        .map(String::trim)
        .doOnNext(value -> System.out.println("received " + value));
}
~~~

Đây là cách viết **không xử lý** những giá trị của nguồn cold: giá trị trả về của `doOnNext` bị bỏ. Một số IDE có thể cảnh báo “result of method call ignored”, nhưng không phải môi trường nào cũng phát hiện được.

### 4.2. Đúng về mặt subscription: xử lý ba loại tín hiệu

~~~java
@Bean
Consumer<Flux<String>> loggingConsumer() {
    return incoming -> incoming
        .map(String::trim)
        .subscribe(
            value -> System.out.println("received " + value),
            error -> System.err.println("stream failed: " + error),
            () -> System.out.println("stream completed")
        );
}
~~~

Lời gọi `subscribe(onNext, onError, onComplete)` khởi động pipeline. Với nguồn cold hữu hạn như `Flux.just(" A ", " B ")`, nó phát hai giá trị rồi hoàn tất. Với nguồn dài hạn, callback hoàn tất có thể không bao giờ được gọi nếu nguồn không phát `onComplete`.

Ví dụ này phù hợp để hiểu cơ chế. Trong production, `System.out` nên được thay bằng logging/metrics phù hợp, và một consumer dài hạn còn cần **giữ và hủy `Disposable`** lúc shutdown.

### 4.3. Vì sao phải truyền callback lỗi?

Một cách viết quá ngắn:

~~~java
incoming.subscribe(value -> sendToExternalSystem(value));
~~~

Nếu pipeline phát `onError` mà không có handler lỗi phù hợp, lỗi có thể bị chuyển tới cơ chế global/drop của Reactor, khó gắn với kết quả nghiệp vụ. Hơn nữa, `sendToExternalSystem` ở đây nếu gọi API blocking có thể làm chặn thread phát dữ liệu.

Một phiên bản có trách nhiệm hơn phải phân biệt lỗi của pipeline với lỗi của hệ thống ngoài và xác định chúng có làm dừng subscription hay được xử lý riêng từng phần tử.

## 5. Vì sao .subscribe() bên trong Consumer vẫn có giới hạn?

Trong `Consumer<Flux<T>>`, việc tự subscribe có thể cần thiết để dữ liệu thực sự được tiêu thụ, nhưng **không biến `void` thành tín hiệu hoàn tất bất đồng bộ**. Có thể hình dung:

~~~mermaid
flowchart LR
    IN["Flux<Order> đầu vào"] --> CON["Consumer.accept(flux)"]
    CON -->|tự subscribe| TASK["Xử lý bất đồng bộ"]
    CON -->|trả void| CALLER["Framework / caller"]
    TASK -->|hoàn tất hoặc lỗi sau đó| LOG["Handler nội bộ"]
    CALLER -.->|không có Mono kết quả| TASK
~~~

Các tình huống cần xét:

- **Caller quay về sớm:** `accept` có thể trả ngay trong khi thao tác I/O bên trong vẫn chưa hoàn tất.
- **Lỗi không truyền qua return value:** `onError` được xử lý bằng callback/subscription nội bộ; caller không tự có `Mono` để quan sát.
- **Hủy subscription:** nếu không lưu `Disposable` hoặc cơ chế quản lý tương ứng, khó chủ động hủy khi binding đóng hoặc ứng dụng shutdown.
- **Retry và at-least-once:** nếu nguồn được subscribe lại, dữ liệu có thể phát lại; thao tác side effect cần idempotency.
- **Ack/offset/transaction:** không được giả định binder chỉ xác nhận message sau khi tác vụ bất đồng bộ bên trong custom `subscribe()` hoàn tất.

Cũng không nên tự subscribe hai lần chỉ để vừa log vừa ghi database:

~~~java
Consumer<Flux<String>> wrong = flux -> {
    flux.subscribe(value -> System.out.println(value));
    flux.subscribe(value -> externalWrite(value));
};
~~~

Với nguồn cold, hai subscription có thể **đọc lại nguồn hai lượt**. Với nguồn hot, hai subscriber có thể nhận các phần tử khác nhau theo thời điểm. Hãy ghép các thao tác trong **một pipeline**, chọn rõ thứ tự và chính sách lỗi.

## 6. Cách được ưu tiên: Function<Flux<T>, Mono<Void>>

Tài liệu Spring Cloud Stream khuyên trong phần lớn trường hợp sử dụng:

~~~java
Function<Flux<T>, Mono<Void>>
~~~

và kết thúc pipeline bằng `then()`. Cách này giữ được đầu ra mô tả **kết thúc hay lỗi**, giúp framework/caller có một publisher để quản lý subscription theo hợp đồng adapter.

Ví dụ xử lý đơn hàng với một repository reactive. Giả sử có record và interface:

~~~java
public record OrderEvent(String orderId, long amountCents) {}

public interface OrderAuditRepository {
    // Ghi thành công: onComplete; lỗi: onError.
    Mono<Void> append(OrderEvent event);
}
~~~

Cấu hình function:

~~~java
package demo.functions;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Configuration
public class OrderAuditFunctions {

    public record OrderEvent(String orderId, long amountCents) {}

    public interface OrderAuditRepository {
        Mono<Void> append(OrderEvent event);
    }

    @Bean
    public Function<Flux<OrderEvent>, Mono<Void>> auditOrders(
            OrderAuditRepository repository) {

        return incoming -> incoming
            .concatMap(repository::append)
            .then();
    }
}
~~~

Ở đây:

1. `auditOrders.apply(incoming)` **trả `Mono<Void>`**, chưa phải là bằng chứng ghi dữ liệu đã xong.
2. Khi caller/adapter subscribe kết quả, `concatMap` gọi `repository.append` cho các phần tử và đợi publisher của từng thao tác hoàn tất theo thứ tự.
3. `then()` bỏ qua mọi `onNext` của pipeline, chỉ phát `onComplete` nếu toàn bộ upstream hoàn tất bình thường; lỗi được truyền qua `onError`.
4. Nếu nguồn vào là một `Flux` không kết thúc, `Mono<Void>` cũng **không hoàn tất thành công** trong khi luồng còn chạy. Các tác vụ ghi vẫn được thực hiện khi nguồn phát dữ liệu.

**Điểm quan trọng:** Giải pháp trả `Mono<Void>` chỉ cải thiện khả năng quan sát khi caller/adapter **thực sự subscribe và quản lý publisher kết quả**. Không nên hứa rằng chỉ đổi chữ ký là binder sẽ tự cung cấp acknowledgment từng message. Cần integration test ở môi trường Spring Cloud Stream đang dùng.

### 6.1. So sánh trực tiếp hai cách viết

| Tiêu chí | `Consumer<Flux<T>>` tự subscribe | `Function<Flux<T>, Mono<Void>>` |
| --- | --- | --- |
| Kiểu trả về | `void` | `Mono<Void>` |
| Ai subscribe pipeline xử lý? | Code consumer phải chủ động | Caller/adapter có thể subscribe kết quả |
| Theo dõi hoàn tất/lỗi | Callback hoặc cơ chế quản lý trong consumer | Qua tín hiệu `onComplete` / `onError` của publisher trả về |
| Hủy pipeline | Consumer cần lưu/quản lý subscription | Caller/adapter có thể hủy subscription vào publisher |
| Phù hợp composition | Có hạn chế do kết thúc bằng `void` | Có publisher kết quả cho contract reactive |
| Với luồng vô hạn | Subscription thường sống dài hạn | `Mono<Void>` thường không có `onComplete` cuối luồng |
| Mặc định đảm bảo delivery broker | Không | Không |

Không phải `Function<Flux<T>, Mono<Void>>` luôn tốt hơn trong mọi adapter. Điểm khác biệt là nó **diễn đạt rõ một tác vụ bất đồng bộ có thể hoàn tất hoặc lỗi**.

### 6.2. Vì sao không viết map(repository::append)?

Đây là lỗi thường gặp khi thao tác repository trả `Mono<Void>`:

~~~java
// Sai mục đích: tạo Flux<Mono<Void>>,
// chưa đảm bảo các Mono được subscribe.
Flux<Mono<Void>> nested = incoming.map(repository::append);
~~~

`map` chỉ tạo publisher con và phát nó dưới dạng một giá trị, không tự subscribe từng `Mono` đó. Dùng:

~~~java
Mono<Void> completed = incoming
    .concatMap(repository::append)
    .then();
~~~

hoặc khi cho phép các thao tác đồng thời, cân nhắc:

~~~java
Mono<Void> completed = incoming
    .flatMap(repository::append, 8)
    .then();
~~~

`flatMap(..., 8)` giới hạn tối đa tám inner publishers đồng thời và **không đảm bảo thứ tự hoàn tất**. Nếu đơn hàng cần thứ tự ghi chính xác, `concatMap` thường dễ suy luận hơn.

## 7. Khi bắt buộc dùng Consumer<Flux<T>>: quản lý Disposable

Có adapter hoặc thiết kế yêu cầu một `Consumer<Flux<T>>` đúng nghĩa. Khi đó, không chỉ gọi `subscribe()` rồi bỏ qua kết quả. Reactor trả một `Disposable` đại diện cho subscription, có thể dùng để hủy.

Ví dụ đơn giản với **một luồng đang hoạt động tại một thời điểm**:

~~~java
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Consumer;

import reactor.core.Disposable;
import reactor.core.publisher.Flux;

public final class ControlledLoggingConsumer
        implements Consumer<Flux<String>>, AutoCloseable {

    private final AtomicReference<Disposable> current =
        new AtomicReference<>();

    @Override
    public void accept(Flux<String> source) {
        Disposable subscription = source.subscribe(
            value -> System.out.println("received: " + value),
            error -> System.err.println("failed: " + error),
            () -> System.out.println("completed")
        );

        Disposable previous = current.getAndSet(subscription);
        if (previous != null) {
            previous.dispose();
        }
    }

    @Override
    public void close() {
        Disposable active = current.getAndSet(null);
        if (active != null) {
            active.dispose();
        }
    }
}
~~~

Trong mẫu này, mỗi lần `accept` được gọi, subscription cũ bị hủy. **Đây là chính sách một subscription duy nhất**, không phải cách quản lý tổng quát cho consumer có nhiều nguồn độc lập. Nếu adapter có thể cung cấp nhiều `Flux` đồng thời, cần cơ chế quản lý nhiều `Disposable`, giới hạn số nguồn và đồng bộ lifecycle phù hợp.

Một vấn đề khác: đoạn mã trên minh họa `AutoCloseable`, nhưng **Spring sẽ chỉ tự gọi lifecycle method theo hợp đồng bean được Spring quản lý**. Nếu tự tạo `new ControlledLoggingConsumer()` rồi bỏ, không có ai tự gọi `close()`. Khi đăng ký bean, có thể dùng:

~~~java
@Bean
ControlledLoggingConsumer controlledLoggingConsumer() {
    return new ControlledLoggingConsumer();
}
~~~

Với bean implements `AutoCloseable`, cơ chế destroy method/lifecycle của Spring cần được kiểm chứng trong cấu hình ứng dụng; có thể khai báo tường minh:

~~~java
@Bean(destroyMethod = "close")
ControlledLoggingConsumer controlledLoggingConsumer() {
    return new ControlledLoggingConsumer();
}
~~~

Đây là **một lựa chọn thay thế** cho bean declaration phía trên, không khai báo cả hai đồng thời. Trong ứng dụng có ràng buộc delivery, còn phải quyết định cách đợi tác vụ đang chạy hoàn tất trước khi hủy, thay vì chỉ gọi `dispose()` đột ngột.

### 7.1. Những giới hạn của Disposable

- `dispose()` yêu cầu hủy subscription; khả năng hủy tức thì một I/O bên ngoài tùy client và việc nó hỗ trợ cancellation.
- `dispose()` không tự rollback giao dịch đã commit hoặc xóa message đã gửi.
- Hủy không đồng nghĩa thành công; cần phân biệt `CANCEL`, `ON_COMPLETE` và `ON_ERROR`.
- Một luồng cold đã hoàn tất ngay trước khi gán vào `current` vẫn có thể được lưu dưới dạng handle đã hoàn tất. Với nhiều lời gọi nhanh và phức tạp, cần quản lý danh sách handle/cleanup cẩn thận.

Có thể dùng `doFinally(signal -> ...)` để ghi nhận trạng thái kết thúc; đừng nhầm `doOnComplete` với việc hủy, vì hủy không phát `onComplete` bình thường.

## 8. Xử lý lỗi theo phần tử hay cho cả subscription?

Trong Reactive Streams, `onError` là **tín hiệu kết thúc**. Nếu một thao tác bất đồng bộ ghi lỗi và không được phục hồi, toàn bộ pipeline đang chạy có thể kết thúc. Đặt xử lý lỗi ở đâu quyết định những phần tử sau có cơ hội được xử lý hay không.

Giả sử `repository.append(order)` trả `Mono<Void>`. Nếu muốn **cố gắng từng đơn độc lập** và chính sách nghiệp vụ cho phép bỏ qua lỗi từng đơn, đặt `onErrorResume` bên trong:

~~~java
Function<Flux<OrderEvent>, Mono<Void>> keepProcessing = incoming ->
    incoming
        .concatMap(order ->
            repository.append(order)
                .onErrorResume(error -> {
                    logger.error("Cannot persist order {}", order.orderId(), error);
                    return Mono.empty();
                })
        )
        .then();
~~~

Cách này **không** đảm bảo mọi đơn được lưu thành công. Nó chỉ đảm bảo lỗi của từng thao tác được xử lý trước khi truyền ra ngoài. Phải có cơ chế báo lỗi/đưa vào hàng đợi xử lý lại nếu nghiệp vụ không cho phép mất sự kiện.

Ngược lại:

~~~java
Mono<Void> stoppedOnFirstError = incoming
    .concatMap(repository::append)
    .then();
~~~

Khi `append` lỗi, `Mono<Void>` phát `onError` và upstream có thể bị hủy. Điều này phù hợp với chiến lược fail-fast; nhưng trên nguồn liên tục, nó có thể dừng việc xử lý các message tiếp theo nếu không có cơ chế phục hồi của adapter.

### 8.1. onErrorResume ở ngoài cùng không tiếp tục nguồn cũ

~~~java
Mono<Void> maskedError = incoming
    .concatMap(repository::append)
    .then()
    .onErrorResume(error -> Mono.empty());
~~~

Đây là việc **chuyển lỗi thành hoàn tất**, không phải cách “bỏ qua một phần tử rồi xử lý các phần tử tiếp theo” trên subscription đã kết thúc. Cần chọn phạm vi lỗi đúng với yêu cầu nghiệp vụ.

### 8.2. Retry có thể khiến dữ liệu được xử lý lại

~~~java
Mono<Void> retried = incoming
    .concatMap(repository::append)
    .then()
    .retry(2);
~~~

`retry` thực hiện đăng ký lại upstream khi lỗi. Nếu publisher cold tái phát các phần tử cũ, những đơn đã lưu trước khi lỗi có thể được ghi lại. Chỉ retry side effect nếu có thiết kế idempotency, khóa sự kiện, transaction hoặc checkpoint phù hợp. Với nguồn hot, subscription mới không nhất thiết replay các phần tử đã mất.

## 9. Backpressure, subscribe() và thao tác blocking

Một subscriber cần biết bao nhiêu phần tử downstream có thể nhận. Khi dùng các overload tiện lợi của `Flux.subscribe(...)`, subscriber mặc định thường yêu cầu dữ liệu với **demand không giới hạn**. Điều này không đồng nghĩa có vô hạn dữ liệu ngay lập tức, nhưng có thể làm nguồn nhanh đẩy quá nhiều công việc.

Nếu consumer sử dụng:

~~~java
Consumer<Flux<OrderEvent>> naive = source ->
    source.subscribe(order -> blockingRepository.save(order));
~~~

thì `blockingRepository.save` có thể chạy trực tiếp trên thread phát dữ liệu và chặn thread đó. Đặc biệt với event loop, đây là thiết kế nguy hiểm.

### 9.1. Tích hợp API blocking một cách có kiểm soát

Nếu chưa thể đổi repository, có thể bọc API blocking bằng `Mono.fromRunnable` và tách nó sang bounded elastic scheduler:

~~~java
Function<Flux<OrderEvent>, Mono<Void>> storeBlocking =
    incoming -> incoming
        .concatMap(order ->
            Mono.fromRunnable(
                    () -> blockingRepository.save(order)
                )
                .subscribeOn(
                    reactor.core.scheduler.Schedulers.boundedElastic()
                )
        )
        .then();
~~~

`blockingRepository` là dependency giả định, còn `save` là phương thức blocking trả `void`. Cách này chỉ **di chuyển thao tác blocking** sang scheduler phù hợp, không biến nó thành I/O non-blocking. Vẫn cần timeout, giới hạn kết nối và xác định số tác vụ đồng thời.

### 9.2. Dùng BaseSubscriber khi cần kiểm soát demand rõ ràng

Đối với một pipeline **xử lý đồng bộ rất nhanh**, có thể minh họa request từng phần tử:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;

BaseSubscriber<String> subscriber = new BaseSubscriber<>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(1);
    }

    @Override
    protected void hookOnNext(String value) {
        System.out.println("received " + value);
        request(1);
    }

    @Override
    protected void hookOnError(Throwable throwable) {
        System.err.println("stream failed: " + throwable);
    }
};

Flux.just("A", "B", "C").subscribe(subscriber);
~~~

Ví dụ giúp hiểu Reactive Streams `request(n)`. Nhưng nếu mỗi phần tử phải ghi I/O **bất đồng bộ**, việc gọi `request(1)` ngay trong `hookOnNext` **chưa bảo đảm đã đợi thao tác ghi xong**. Khi đó cần ghép `concatMap`/`flatMap` với publisher của thao tác I/O, đặt concurrency và chính sách lỗi rõ ràng.

Backpressure nội bộ Reactor cũng không tự làm broker hoặc hệ thống ngoài giảm tốc; binder và connector phải hỗ trợ cơ chế điều tiết tương ứng.

## 10. Consumer và các nguồn Flux hữu hạn, dài hạn

| Đặc điểm | Flux hữu hạn | Flux dài hạn |
| --- | --- | --- |
| Ví dụ | `Flux.just(a,b,c)` | `Flux.interval(...)`, event stream |
| Có `onComplete` bình thường? | Có | Thường không cho tới khi đóng nguồn |
| `Consumer<Flux<T>>` tự subscribe | Nhận phần tử và completion callback | Subscription tiếp tục cho tới lỗi/hủy |
| `Function<Flux<T>,Mono<Void>>` | `then()` hoàn tất khi nguồn và tác vụ con hoàn tất | Có thể chạy mãi mà `Mono<Void>` chưa `onComplete` |
| Đóng ứng dụng | Subscription có thể đã kết thúc | Cần hủy/đóng tài nguyên chủ động |
| Kiểm thử | `StepVerifier.verifyComplete()` | Test bounded với `take(n)` hoặc cancellation |

Không phải “mỗi khi nhận message, consumer reactive được gọi lại”. Trong nhiều tích hợp theo mô hình luồng, consumer có thể nhận **một `Flux<T>` dài hạn**; các giá trị được phát theo `onNext` trong subscription. Với một adapter HTTP hay caller Java trực tiếp, có thể có một invocation mới cho mỗi request. Phải đo và xác nhận ở integration test thay vì suy đoán từ chữ ký.

## 11. Consumer<Message<T>> và Consumer<Flux<Message<T>>>

Đối với xử lý sự kiện, payload có thể không đủ: cần correlation ID, routing key, event ID hay header của message. Khi đó có thể sử dụng `Message<T>` của Spring Messaging.

### 11.1. Consumer imperative nhận từng message

~~~java
@Bean
Consumer<Message<String>> auditOneMessage() {
    return message -> {
        String eventId = (String) message
            .getHeaders()
            .get("eventId");

        System.out.println(
            "received eventId=" + eventId
                + ", payload=" + message.getPayload()
        );
    };
}
~~~

Một adapter có thể gọi consumer này theo từng message, với headers tương ứng. Quy tắc chuyển đổi kiểu, retry và acknowledgment do adapter/binder quyết định.

### 11.2. Consumer reactive nhận cả luồng message

~~~java
@Bean
Consumer<Flux<Message<String>>> auditMessageStream() {
    return messages -> messages.subscribe(
        message -> {
            Object eventId = message.getHeaders().get("eventId");
            System.out.println(
                eventId + ": " + message.getPayload()
            );
        },
        error -> System.err.println("stream failed: " + error)
    );
}
~~~

Ở đây header được đọc **cho từng `Message<String>`**, không phải một header chung cho toàn `Flux`. Đầu vào có thể chứa message của nhiều correlation ID.

**Cảnh báo:** Nếu header mang đối tượng acknowledgment do binder thêm vào, việc gọi thủ công acknowledgment bên trong subscription cần tuân thủ đúng tài liệu của binder và chế độ delivery đang dùng. Không tự suy luận rằng xử lý xong `onNext` là có thể commit an toàn, đặc biệt nếu công việc chính là bất đồng bộ.

## 12. FunctionCatalog, composition và reactive Consumer

Spring Cloud Function có thể ghép các bean function tương thích thành pipeline. Ví dụ function reactive lọc và consumer imperative:

~~~java
@Bean
Function<Flux<String>, Flux<String>> trimStream() {
    return source -> source.map(String::trim);
}

@Bean
Consumer<String> printOne() {
    return System.out::println;
}
~~~

Có thể chọn composition bằng tên, ví dụ:

~~~properties
spring.cloud.function.definition=trimStream|printOne
~~~

Tuy nhiên, **ghép reactive function với imperative consumer có một giới hạn** được tài liệu Spring Cloud Stream nhấn mạnh: composition kết thúc ở một reactive `Consumer`. Vì kết quả cuối cùng có kiểu `void`, framework không có publisher kết quả để subscribe; nếu không có bước xử lý subscription thích hợp, pipeline có thể không chạy như mong đợi.

Do đó, không nên coi mọi composition hợp lệ về mặt kiểu là đã có vòng đời subscription đúng.

### 12.1. Các hướng xử lý

- **Nếu xử lý từng message độc lập:** cân nhắc dùng cả hai bước ở dạng imperative, `Function<T,R>` rồi `Consumer<R>`, để adapter gọi theo từng message.
- **Nếu xử lý cả luồng:** cân nhắc viết function reactive cuối cùng trả publisher, chẳng hạn `Function<Flux<T>, Mono<Void>>`, và để caller/adapter subscribe kết quả theo hợp đồng hỗ trợ.
- **Nếu thực sự cần reactive Consumer:** triển khai subscription, lỗi và lifecycle tường minh theo hướng dẫn của adapter.

Một phiên bản trả publisher có thể là:

~~~java
@Bean
Function<Flux<String>, Mono<Void>> printStream() {
    return source -> source
        .doOnNext(System.out::println)
        .then();
}
~~~

`doOnNext` ở ví dụ này là **side effect đồng bộ nhỏ** nhằm minh họa. Nếu cần ghi database hoặc gửi HTTP bất đồng bộ, dùng `concatMap`/`flatMap` để đưa publisher tác vụ con vào pipeline và truyền lỗi đúng cách.

## 13. HTTP, broker và serverless: trách nhiệm nào thay đổi?

Spring Cloud Function tách logic Java khỏi giao thức, nhưng **hợp đồng subscription và hoàn tất** vẫn phụ thuộc adapter.

| Môi trường | Điều phải làm rõ |
| --- | --- |
| Gọi Java thuần | Caller gọi `accept` với publisher, nhưng không nhận kết quả để biết hoàn tất; unit test cần tự quản lý tín hiệu |
| `FunctionCatalog` | Catalog tra cứu/wrap function, không biến `Consumer<Flux<T>>` thành publisher có thể quan sát chỉ nhờ tên |
| Spring Cloud Stream binder | Cách cung cấp `Flux`, subscription, retry/ack, partition và shutdown; reactive Consumer phải tự subscribe khi khai báo tường minh |
| HTTP adapter | Request có thể kết thúc sau khi `accept` trả `void`; phải xác định liệu và khi nào I/O bất đồng bộ thực sự hoàn tất |
| Serverless adapter | Invocation có timeout; không mặc định một fire-and-forget subscription sẽ còn chạy sau khi invocation kết thúc |

Với các tác vụ quan trọng như thanh toán, phát hóa đơn hoặc ghi outbox, hãy tránh chọn một kiểu `Consumer<Flux<T>>` chỉ vì cú pháp gọn. Cần có cơ chế để caller/binder biết thời điểm đủ điều kiện acknowledgment, và cách xử lý khi hệ thống dừng giữa chừng.

### 13.1. Subscription không phải acknowledgment

**Subscribe thành công** chỉ cho biết pipeline đã được đăng ký. Nó không chứng minh:

- Message đã được ghi vào database.
- Kết quả đã commit bền vững.
- Broker đã nhận được acknowledgment.
- Một event không thể được xử lý lại.
- Một subscription không bị hủy giữa chừng.

Những bảo đảm này đến từ thiết kế giao dịch, idempotency, offset/acknowledgment và hợp đồng binder cụ thể.

## 14. Kiểm thử: có subscription hay chỉ tạo pipeline?

### 14.1. Unit test phát hiện consumer quên subscribe

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Consumer;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;

class ReactiveConsumerTest {

    @Test
    void aPipelineWithoutSubscriptionDoesNotConsumeColdFlux() {
        AtomicInteger processed = new AtomicInteger();

        Consumer<Flux<Integer>> wrong = source -> {
            source.doOnNext(value -> processed.incrementAndGet());
        };

        wrong.accept(Flux.just(1, 2, 3));

        assertEquals(0, processed.get());
    }

    @Test
    void explicitSubscriptionConsumesColdFlux() {
        AtomicInteger processed = new AtomicInteger();

        Consumer<Flux<Integer>> correct = source ->
            source.subscribe(
                value -> processed.incrementAndGet(),
                error -> { throw new AssertionError(error); }
            );

        correct.accept(Flux.just(1, 2, 3));

        // Flux.just phát đồng bộ trong trường hợp đơn giản này.
        assertEquals(3, processed.get());
    }
}
~~~

Bài test thứ hai đúng với nguồn đồng bộ `Flux.just`. Với HTTP/database bất đồng bộ hoặc `Flux.interval`, **đừng kiểm tra ngay sau `accept` rồi kỳ vọng đã xong**. Cần chờ tín hiệu rõ ràng, dùng cơ chế đồng bộ test với timeout hữu hạn hoặc kiểm thử function trả publisher.

### 14.2. Test function trả Mono<Void> bằng StepVerifier

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ReactiveFunctionCompletionTest {

    @Test
    void completionMeansAllItemsWereProcessed() {
        AtomicInteger saved = new AtomicInteger();

        Function<Flux<Integer>, Mono<Void>> process = numbers ->
            numbers
                .concatMap(number ->
                    Mono.fromRunnable(saved::incrementAndGet)
                )
                .then();

        Mono<Void> completion = process.apply(
            Flux.just(10, 20, 30)
        );

        // Chưa subscribe: chưa có side effect.
        assertEquals(0, saved.get());

        StepVerifier.create(completion)
            .verifyComplete();

        assertEquals(3, saved.get());
    }

    @Test
    void anErrorIsObservable() {
        Function<Flux<Integer>, Mono<Void>> process = numbers ->
            numbers
                .concatMap(number -> number == 2
                    ? Mono.<Void>error(
                        new IllegalStateException("invalid item")
                      )
                    : Mono.<Void>empty()
                )
                .then();

        StepVerifier.create(process.apply(Flux.just(1, 2, 3)))
            .expectErrorMessage("invalid item")
            .verify();
    }
}
~~~

`StepVerifier` kiểm tra cả tín hiệu hoàn tất và lỗi. Đó là lợi ích của việc trả publisher thay vì chỉ dùng `void`.

### 14.3. Cần integration test gì?

Khi đưa consumer qua Spring Cloud Stream hoặc adapter khác, hãy xác nhận thực tế:

1. `spring.cloud.function.definition` chọn đúng bean.
2. Bean nhận đúng payload/header theo hợp đồng.
3. Reactive consumer có subscription thật và xử lý nhiều message liên tiếp.
4. Lỗi của repository/API có được phát hiện và được xử lý theo chính sách mong muốn.
5. Shutdown/rebalance có dừng subscription hoặc thoát sạch không.
6. Nếu muốn thứ tự, `flatMap`/`concatMap` có giữ đúng ràng buộc không.
7. Retry hoặc restart có thể làm message lặp không và idempotency có bảo vệ không.
8. Ack/offset/transaction thực sự xảy ra ở mốc nào so với việc lưu thành công.

Unit test Reactor **không thể thay thế** kiểm thử tương tác với binder và broker.

## 15. Các lỗi thường gặp và hướng xử lý

| Triệu chứng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| Consumer được gọi nhưng không có log dữ liệu | Chỉ gọi `map`/`doOnNext` mà không subscribe | Nếu bắt buộc dùng `Consumer<Flux<T>>`, subscribe rõ ràng; hoặc trả publisher từ `Function` |
| Function trả `Mono<Void>` nhưng không ghi gì | Caller không subscribe publisher kết quả | Kiểm tra hợp đồng adapter/caller và subscription |
| Một lỗi làm dừng cả dòng sự kiện | `onError` không được xử lý trong pipeline dài hạn | Chọn phạm vi phục hồi từng phần tử hoặc để fail và restart có kiểm soát |
| Có lỗi nhưng caller nghĩ thành công | `Consumer.accept` trả `void` trước khi xử lý bất đồng bộ xong | Dùng function trả publisher khi cần quan sát hoàn tất |
| Xử lý trùng sau retry | Subscription mới replay nguồn cold | Idempotency, checkpoint và chính sách retry phù hợp |
| Tác vụ chậm làm nghẽn nguồn | Blocking I/O trong `subscribe(onNext)` | Repository reactive hoặc cô lập blocking và giới hạn concurrency |
| Mất trật tự kết quả | Dùng `flatMap` xử lý song song | Dùng `concatMap` hoặc `flatMapSequential` phù hợp |
| Có nhiều lần xử lý cùng phần tử | Subscribe nhiều lần vào publisher cold | Tạo một pipeline, quản lý subscription duy nhất trong phạm vi phù hợp |
| Tắt ứng dụng còn nguồn hoạt động | Không lưu/hủy `Disposable` | Quản lý lifecycle và cancellation bằng bean/container |
| Consumer ghép composition không chạy | Composition kết thúc bằng reactive Consumer trả `void` | Chọn cấu trúc composition có publisher kết quả hoặc cấu hình consumer phù hợp |
| Broker nhận message nhưng DB chưa ghi | Nhầm thời điểm subscribe với thời điểm hoàn tất side effect | Xác định ack/transaction của binder bằng integration test |
| Test với `Flux.just` PASS nhưng runtime lỗi | Test đồng bộ không bao phủ cancellation, I/O và transport | Bổ sung test với nguồn bất đồng bộ và broker thực |

## 16. Cách chọn chữ ký theo trách nhiệm

~~~mermaid
flowchart TD
    START["Cần xử lý dữ liệu đầu vào"] --> Q1{"Cần xử lý từng T độc lập?"}
    Q1 -->|Có| SINGLE["Consumer<T> / Function<T,R>"]
    Q1 -->|Không, xử lý một Flux| Q2{"Caller cần biết khi nào\nxử lý xong hoặc bị lỗi?"}
    Q2 -->|Có| FUNCTION["Function<Flux<T>,Mono<Void>>"]
    Q2 -->|Không, adapter quy định\nConsumer<Flux<T>>| CONSUMER["Consumer<Flux<T>>"]
    CONSUMER --> SUB["Chủ động subscribe()\n+ onError + lifecycle"]
    FUNCTION --> DELEGATE["Trả publisher;\ncaller/adapter subscribe"]
    SINGLE --> VERIFY["Kiểm chứng delivery,\nretry, ack và idempotency"]
    SUB --> VERIFY
    DELEGATE --> VERIFY
~~~

Để lựa chọn chính xác, hãy trả lời năm câu hỏi:

- **Ai gọi `accept` hoặc `apply`?** Một lần cho mỗi message, hay một lần cung cấp publisher dài hạn?
- **Ai subscribe?** Framework có publisher kết quả để quản lý, hay consumer phải tự subscribe?
- **Ai nhận `onError` và `onComplete`?** Lỗi cần dừng toàn pipeline hay chỉ một tác vụ con?
- **Ai hủy nguồn?** Shutdown, rebalance, timeout và mạng ngắt phải được xử lý như thế nào?
- **Khi nào message được coi đã xử lý?** Sau khi subscribe, sau khi tác vụ hoàn tất, hay sau khi transaction/ack thành công?

Một thiết kế dễ bảo trì phải có câu trả lời rõ ràng trước khi kết nối với broker hoặc hệ thống bên ngoài.

## 17. Câu hỏi tự đánh giá

1. Vì sao `Consumer<Flux<String>>` gọi `flux.map(...)` mà không subscribe sẽ không xử lý nguồn cold?
2. Tại sao `Consumer<Flux<T>>` khiến framework không có tham chiếu publisher kết quả để tự subscribe?
3. Điểm khác nhau giữa `Consumer<T>` được adapter gọi cho từng message và `Consumer<Flux<T>>` nhận một luồng dài hạn là gì?
4. Nếu consumer tự gọi `subscribe()` rồi `accept` trả `void`, caller có biết ghi database đã thành công chưa?
5. `Function<Flux<T>, Mono<Void>>` giúp truyền tín hiệu lỗi và hoàn tất như thế nào? Có tự đảm bảo broker ack đúng lúc không?
6. Vì sao `map(repository::save)` có thể tạo `Flux<Mono<Void>>` mà chưa lưu dữ liệu? Nên dùng toán tử nào?
7. Một subscription gặp `onError` sẽ tiếp tục nhận phần tử tiếp theo trong cùng subscription không?
8. Vì sao cần giữ `Disposable` nếu consumer nhận một `Flux` dài hạn?
9. Nếu cùng nguồn cold được subscribe hai lần, việc ghi dữ liệu có thể xảy ra bao nhiêu lần?
10. Khi ghép reactive `Function` với imperative `Consumer` trong composition, cần kiểm tra giới hạn nào?
11. Tại sao overload `subscribe(onNext)` tiện lợi không thay thế một chiến lược backpressure và xử lý lỗi?
12. Vì sao `StepVerifier.verifyComplete()` kiểm chứng một chức năng khác với việc khẳng định broker đã xác nhận message?

## 18. Tài liệu tham khảo

- [Spring Cloud Function — Programming model, Consumer](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html)
- [Spring Cloud Stream — Producing and Consuming Messages, Consumer (Reactive)](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html)
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/)
- [Project Reactor — Test bằng StepVerifier](https://projectreactor.io/docs/test/release/reference/)

Các cơ chế gọi/subscribe, ack và lifecycle phụ thuộc phiên bản Spring Cloud Function, Spring Cloud Stream và binder. Tài liệu chính thức là điểm đối chiếu cho từng stack thực tế; ví dụ test Reactor thuần chưa phải bằng chứng hành vi của adapter production.

**Ghi nhớ:** `Consumer<Flux<T>>` **không tự chạy các toán tử Reactor** chỉ vì nhận một `Flux`. Do `accept` trả `void`, nếu dùng reactive consumer tường minh, bạn phải chủ động **subscribe** và quản lý lỗi, hủy cũng như tác vụ chưa hoàn tất. Khi cần caller hoặc adapter quan sát hoàn tất, hãy cân nhắc `Function<Flux<T>, Mono<Void>>` với `then()` để đưa tín hiệu kết thúc/lỗi vào publisher trả về. Trong cả hai trường hợp, chất lượng xử lý sự kiện còn phụ thuộc cơ chế retry, idempotency, acknowledgment và quản lý vòng đời của adapter.
