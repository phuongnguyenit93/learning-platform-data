# Phân biệt reactive function với Reactive Kafka Binder và kiểm tra tình trạng hỗ trợ

Trong Spring Cloud Stream, viết hàm nhận hoặc trả về Flux hay Mono chưa đủ để kết luận toàn bộ ứng dụng đang xử lý reactive từ broker đến broker. Reactive function mô tả cách mã ứng dụng làm việc với một luồng dữ liệu. Binder quyết định cách Spring Cloud Stream kết nối luồng đó với Kafka, RabbitMQ hoặc Pulsar. Nếu binder sử dụng API message channel theo kiểu imperative, các toán tử Reactor vẫn có thể chạy bên trong hàm nhưng ranh giới giao nhận với broker không tự động trở thành Reactive Streams.

Reactive Kafka Binder từng cung cấp đường kết nối Kafka dựa trên Reactor Kafka, dùng KafkaReceiver và KafkaSender để hỗ trợ backpressure xuyên suốt hơn. Tuy nhiên, Reactor Kafka đã được thông báo ngừng phát triển và Reactive Kafka Binder đã bị deprecated, có thông tin loại bỏ artifact ở một số release train. Vì vậy, khi học hoặc bảo trì Spring Cloud Stream, cần phân biệt rõ khả năng reactive của function với tình trạng hỗ trợ của binder theo đúng phiên bản đang sử dụng.

## 1. Hai lớp khác nhau: reactive function và reactive binder

Reactive function thuộc mô hình lập trình của Spring Cloud Function. Nó dùng kiểu dữ liệu của Project Reactor như Flux<T> và Mono<T> để biểu diễn một luồng nhiều phần tử hoặc một kết quả bất đồng bộ đơn lẻ.

Reactive binder thuộc lớp tích hợp với middleware. Nó phải nhận và gửi dữ liệu bằng API reactive của broker/client để demand và backpressure có thể truyền qua ranh giới ứng dụng đến nguồn dữ liệu.

| Khái niệm | Trách nhiệm | Ví dụ |
|---|---|---|
| Reactive function | Xử lý luồng dữ liệu bằng Reactor | Function<Flux<Order>, Flux<OrderView>> |
| Imperative Kafka binder | Nối binding với Kafka bằng message channel/listener container | spring-cloud-starter-stream-kafka |
| Reactive Kafka Binder | Nối binding với Kafka bằng Reactor Kafka API | spring-cloud-stream-binder-kafka-reactive trong các phiên bản từng cung cấp artifact |
| Reactive Streams | Giao thức Publisher/Subscriber có demand và backpressure | Flux, Mono, Subscription |

Điểm phân biệt quan trọng là reactive API trong hàm không tự biến binder thành reactive. Một Function<Flux<T>, Flux<R>> có thể chạy với binder Kafka thông thường, nhưng chỉ phần xử lý trong function có ngữ nghĩa Reactor. Khi binder là message-channel based, việc lấy record từ Kafka và gửi record ra Kafka vẫn chịu cơ chế của binder thông thường.

## 2. Reactive function hoạt động như thế nào?

Spring Cloud Function hỗ trợ Supplier, Function và Consumer với kiểu reactive. Ví dụ, một Function có thể nhận Flux<OrderEvent>, lọc sự kiện và biến đổi từng phần tử:

~~~java
import java.util.function.Function;
import reactor.core.publisher.Flux;

public record OrderEvent(String orderId, int quantity) {}

public record OrderView(String orderId, String category) {}

@Bean
Function<Flux<OrderEvent>, Flux<OrderView>> toOrderView() {
    return events -> events
        .filter(event -> event.quantity() > 0)
        .map(event -> new OrderView(
            event.orderId(),
            event.quantity() >= 10 ? "BULK" : "NORMAL"
        ));
}
~~~

Hàm trên không được gọi một lần cho từng OrderEvent theo cách của một Function imperative. Reactive function là hàm khởi tạo luồng: framework gọi nó để lấy Flux đầu ra và kết nối luồng đó với luồng đầu vào. Sau đó các toán tử được thực thi khi dữ liệu đi qua pipeline.

~~~mermaid
flowchart LR
    A["Flux<OrderEvent>"] --> B["filter"]
    B --> C["map"]
    C --> D["Flux<OrderView>"]
~~~

Các toán tử như map, filter, concatMap, flatMap và onErrorResume mô tả cách dữ liệu được xử lý. Khi có subscriber và demand, các phần tử mới được phát qua pipeline. Một số toán tử tạo thêm buffer hoặc prefetch nội bộ, vì vậy cần chọn toán tử và giới hạn concurrency phù hợp với tải.

## 3. Reactive function với Kafka binder thông thường

Ứng dụng có thể khai báo reactive function nhưng vẫn dùng Kafka binder dựa trên message channel. Ví dụ dependency:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-stream-kafka</artifactId>
</dependency>
~~~

Cấu hình binding:

~~~yaml
spring:
  cloud:
    function:
      definition: toOrderView
    stream:
      bindings:
        toOrderView-in-0:
          destination: orders.events
          group: order-viewer
          content-type: application/json
        toOrderView-out-0:
          destination: orders.views
          content-type: application/json
~~~

Trong cấu hình này, toOrderView là reactive function, nhưng binder được chọn là Kafka binder thông thường. Spring Cloud Stream vẫn sử dụng cơ chế message channel và consumer/producer của binder để trao đổi với Kafka.

Điều ứng dụng nhận được:

- Có thể dùng Flux và Mono để viết pipeline xử lý dữ liệu.
- Có thể dùng các toán tử Reactor để biến đổi, kết hợp hoặc xử lý bất đồng bộ trong phạm vi function.
- Có thể tổ chức code theo mô hình reactive mà không phải chuyển toàn bộ nghiệp vụ sang callback hoặc imperative loop.

Điều ứng dụng không tự nhận được chỉ nhờ dùng Flux/Mono:

- Backpressure từ subscriber không tự truyền xuyên qua message channel đến Kafka fetch loop.
- Kafka producer/consumer không tự trở thành KafkaSender/KafkaReceiver reactive.
- Không nên suy ra khả năng điều tiết tải toàn tuyến chỉ từ chữ ký reactive của function.

Vì vậy, reactive function với binder thông thường thường là mô hình reactive ở lớp xử lý. Ranh giới với broker vẫn theo mô hình của binder đó.

## 4. Reactive Kafka Binder từng cung cấp điều gì?

Reactive Kafka Binder là một binder riêng dựa trên Reactor Kafka. Ở phía nhận, binder sử dụng KafkaReceiver để tạo luồng record reactive. Ở phía gửi, binder sử dụng KafkaSender để publish record. Khi cả hai đầu đều được kết nối bằng API reactive, demand và backpressure có thể tham gia vào quá trình tiêu thụ và phát dữ liệu.

Sơ đồ khái niệm:

~~~mermaid
flowchart LR
    K[("Kafka topic")] --> R["KafkaReceiver"]
    R --> F["Reactive function<br/>Flux / Mono"]
    F --> S["KafkaSender"]
    S --> O[("Kafka topic")]
    F -. "Demand / backpressure" .-> R
    S -. "Reactive send result" .-> F
~~~

Function ví dụ:

~~~java
@Bean
Function<Flux<String>, Flux<String>> uppercase() {
    return values -> values.map(String::toUpperCase);
}
~~~

Về mặt chữ ký, function này có thể chạy với cả Kafka binder thông thường và Reactive Kafka Binder. Khác biệt nằm ở đường kết nối phía dưới:

| Thành phần | Kafka binder thông thường | Reactive Kafka Binder |
|---|---|---|
| Consumer phía broker | Kafka listener/message channel | Reactor Kafka KafkaReceiver |
| Producer phía broker | Kafka producer/message channel | Reactor Kafka KafkaSender |
| Reactive function | Có thể dùng | Có thể dùng |
| Backpressure ở trong function | Có, trong phạm vi Reactor pipeline | Có |
| Backpressure xuyên ranh giới Kafka | Không được bảo đảm bởi binder message-channel based | Là mục tiêu của reactive binder |
| Tình trạng hiện nay | Binder được duy trì trong hệ sinh thái Spring Cloud Stream | Đã deprecated; artifact bị loại bỏ ở một số release train |

Tọa độ Maven của binder cũ từng là:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-stream-binder-kafka-reactive</artifactId>
</dependency>
~~~

Đoạn này chỉ để nhận diện dependency trong ứng dụng cũ. Không sao chép nó vào dự án mới nếu BOM của release train không còn quản lý hoặc release notes đã thông báo loại bỏ.

Đừng thêm cả hai binder rồi mặc định framework sẽ chọn đường reactive. Dependency và binder được chọn phải được xác định rõ trong cấu hình. Nếu ứng dụng có nhiều binder trên classpath, thuộc tính binder của từng binding cũng có thể quyết định binder thực tế.

## 5. Tình trạng hỗ trợ của Reactive Kafka Binder

Tình trạng hỗ trợ đã thay đổi do Reactor Kafka được quyết định ngừng phát triển. Cần đọc release notes của đúng Spring Cloud release train thay vì dựa vào một ví dụ cũ trên blog hoặc một trang reference còn tồn tại.

Các mốc chính được Spring công bố:

| Mốc | Thông tin |
|---|---|
| 20/05/2025 | Project Reactor thông báo Reactor Kafka sẽ ngừng được duy trì trong tương lai; Reactor Kafka Binder của Spring Cloud Stream và reactive template của Spring for Apache Kafka được đánh dấu deprecated và dự kiến loại bỏ |
| Spring Cloud Stream 4.3.0 | Tài liệu Reactive Kafka Binder ghi rõ binder đã deprecated và sẽ bị loại bỏ trong một release tương lai |
| Spring Cloud 2025.1.0 | Release notes ghi artifact org.springframework.cloud:spring-cloud-stream-binder-kafka-reactive đã bị loại khỏi release train vì Reactor Kafka bị discontinued |
| Spring Cloud 2026.0.0 | Thông báo release train tiếp tục liệt kê việc deprecated Reactive Kafka Binder do Reactor Kafka bị discontinued |

Trang reference Reactive Kafka Binder trong tài liệu Spring Cloud Stream 5.1.0 vẫn còn được công bố, nhưng phần đầu trang tiếp tục cảnh báo binder deprecated từ 4.3.0 và sẽ bị loại bỏ trong tương lai. Release notes của các train không hoàn toàn giống nhau về cách diễn đạt giữa deprecated và removed. Vì vậy, sự tồn tại của trang tài liệu không chứng minh artifact còn được phát hành hoặc được hỗ trợ trong BOM cụ thể.

Quy tắc thực hành:

1. Không chọn Reactive Kafka Binder làm mặc định cho dự án mới.
2. Tra release notes của đúng Spring Cloud release train đang dùng.
3. Kiểm tra dependency management/BOM và kho artifact để xác nhận artifact có thực sự tồn tại cho phiên bản đó.
4. Nếu artifact không còn trong train, không ép một version cũ vào dependency graph chỉ để build qua.
5. Nếu đang bảo trì ứng dụng cũ dùng binder này, ghi nhận trạng thái deprecated, đánh giá kế hoạch chuyển đổi và kiểm tra thời hạn hỗ trợ của Reactor Kafka.

## 6. Kiểm tra dependency và phiên bản thực tế

Không nên chỉ nhìn tên dependency trong file build. Hãy kiểm tra dependency tree sau khi import Spring Cloud BOM.

Với Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework.cloud:spring-cloud-stream-binder-kafka-reactive
./mvnw dependency:tree -Dincludes=io.projectreactor.kafka:reactor-kafka
./mvnw help:effective-pom
~~~

Với Gradle:

~~~bash
./gradlew dependencyInsight --dependency spring-cloud-stream-binder-kafka-reactive --configuration runtimeClasspath
./gradlew dependencyInsight --dependency reactor-kafka --configuration runtimeClasspath
./gradlew dependencies --configuration runtimeClasspath
~~~

Khi đọc kết quả:

- Nếu không có artifact reactive binder trong dependency graph, ứng dụng không sử dụng binder đó dù function nhận Flux.
- Nếu artifact xuất hiện từ dependency bắc cầu, xác định module nào kéo nó vào và vì sao.
- Kiểm tra phiên bản Reactor Kafka có khớp với train và BOM đang sử dụng không.
- Kiểm tra log khởi tạo binding để biết binder thực tế được chọn.
- Không override thủ công version Reactor Kafka hoặc binder cũ nếu release train không còn quản lý chúng.

Có thể tra thêm Maven Central bằng đúng tọa độ và phiên bản được release notes công bố. Một kết quả tìm thấy artifact ở phiên bản cũ chỉ xác nhận artifact từng được phát hành, không xác nhận nó còn được duy trì hoặc tương thích với Spring Cloud Stream hiện tại.

## 7. Hướng đi phù hợp cho ứng dụng mới

Tài liệu Spring Cloud Stream hiện hành hướng người dùng tiếp tục dùng Kafka binder dựa trên message channel với reactive types nếu muốn viết function theo Reactor. Các trường hợp reactive cần được xử lý tường minh bằng Project Reactor và cần hiểu giới hạn của binder.

Ví dụ Function xử lý bất đồng bộ với concurrency giới hạn:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderResult>> processOrders(
        OrderService orderService) {
    return events -> events
        .flatMap(orderService::process, 8);
}
~~~

Ở đây flatMap cho phép tối đa tám tác vụ process đồng thời trong phạm vi toán tử. Nếu cần giữ thứ tự hoàn tất theo thứ tự đầu vào, có thể dùng concatMap:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderResult>> processInOrder(
        OrderService orderService) {
    return events -> events
        .concatMap(orderService::process);
}
~~~

Chọn toán tử dựa trên yêu cầu nghiệp vụ:

| Toán tử | Hành vi | Khi nên dùng |
|---|---|---|
| map | Biến đổi đồng bộ từng phần tử | Phép tính nhanh, không gọi I/O |
| concatMap | Chuyển mỗi phần tử thành Publisher và chờ theo thứ tự | Cần xử lý tuần tự hoặc giữ thứ tự đầu ra |
| flatMap | Chạy các Publisher con đồng thời | Cần tăng thông lượng và chấp nhận kết quả có thể về khác thứ tự |
| flatMap với concurrency | Giới hạn số tác vụ con đồng thời | Cần giới hạn số request hoặc kết nối đang hoạt động |
| onErrorResume | Chuyển lỗi thành luồng thay thế | Có chính sách fallback hoặc kết quả lỗi nghiệp vụ |
| retryWhen | Đăng ký lại nguồn khi lỗi theo chính sách | Lỗi tạm thời và thao tác có thể lặp an toàn |

Concurrency trong flatMap chỉ giới hạn tác vụ bên trong pipeline. Nó không tự thay thế cấu hình concurrency của consumer binding và cũng không điều khiển số Kafka partition.

## 8. Reactive Consumer và lý do cần Mono<Void>

Consumer<T> có kiểu trả về void. Khi khai báo Consumer<Flux<T>>, framework không nhận được Publisher trả về để biết khi nào quá trình xử lý reactive hoàn tất hoặc để subscribe vào nó. Vì vậy, tài liệu Spring Cloud Stream khuyến nghị biểu diễn reactive consumer bằng Function<Flux<T>, Mono<Void>> và kết thúc pipeline bằng then().

~~~java
import reactor.core.publisher.Mono;

@Bean
Function<Flux<OrderEvent>, Mono<Void>> saveOrders(
        OrderService orderService) {
    return events -> events
        .concatMap(orderService::save)
        .then();
}
~~~

Mono<Void> cho biết pipeline hoàn tất mà không phát giá trị kết quả. Framework có thể làm việc với Publisher trả về. Nếu thật sự dùng Consumer<Flux<T>>, code phải tự subscribe vào Flux; nếu không, pipeline có thể không được thực thi.

Không nên gọi subscribe() tùy tiện bên trong Function trả Flux hoặc Mono. Việc tự subscribe tạo một luồng xử lý tách khỏi Publisher trả về, khiến framework không còn theo dõi đầy đủ completion, lỗi và lifecycle của pipeline. Chỉ dùng explicit subscribe trong trường hợp API yêu cầu Consumer void và ứng dụng tự chịu trách nhiệm quản lý subscription.

## 9. Error handling và retry trong reactive function

Spring Cloud Stream có cơ chế error handling và retry ở ranh giới imperative message handler. Với imperative function, framework gọi handler cho từng message và có thể bao quanh từng lần gọi bằng cơ chế retry.

Reactive function được gọi để tạo luồng và framework không kiểm soát từng thao tác bên trong sau khi pipeline đã được nối. Do đó, lỗi phát sinh khi Flux chạy cần được xử lý bằng toán tử Reactor.

Ví dụ:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

@Bean
Function<Flux<OrderEvent>, Flux<OrderResult>> processSafely(
        OrderService orderService) {
    return events -> events
        .flatMap(event -> orderService.process(event)
            .onErrorResume(error ->
                Mono.just(OrderResult.failed(event.orderId(), error.getMessage()))
            ), 8);
}
~~~

Ví dụ trên chuyển lỗi của từng đơn hàng thành một kết quả thất bại, để lỗi của một phần tử không nhất thiết kết thúc toàn bộ luồng. Nếu muốn retry, có thể đặt retryWhen quanh Publisher của từng sự kiện:

~~~java
events.flatMap(event ->
    orderService.process(event)
        .retryWhen(Retry.backoff(3, Duration.ofMillis(200)))
        .onErrorResume(error ->
            Mono.just(OrderResult.failed(event.orderId(), "PROCESSING_FAILED"))
        ),
    8
);
~~~

Retry có thể gọi lại thao tác đã thực hiện một phần. Nếu process ghi cơ sở dữ liệu, phát sự kiện hoặc gọi dịch vụ bên ngoài, hãy thiết kế idempotency và timeout. Không nên đặt retry vô hạn hoặc retry mọi loại lỗi; lỗi dữ liệu không hợp lệ thường không tự hết khi thử lại.

## 10. Backpressure không đồng nghĩa với giới hạn tải toàn hệ thống

Backpressure của Reactive Streams cho phép subscriber yêu cầu số phần tử mà nó có thể xử lý. Publisher tương thích có thể điều chỉnh tốc độ phát dựa trên demand. Nhưng để áp dụng từ Kafka đến function và ngược lại, từng thành phần ở ranh giới phải hỗ trợ cơ chế reactive đó.

Với binder Kafka thông thường:

- Kafka consumer được điều khiển bằng cấu hình consumer/listener của binder.
- Message được chuyển qua cơ chế message channel.
- Reactive function có thể xử lý các Publisher trong nội bộ.
- Demand trong Flux không tự động truyền ngược thành yêu cầu giảm fetch từ Kafka consumer.

Vì vậy, khi sử dụng binder thông thường, vẫn cần thiết kế các giới hạn vận hành:

- Giới hạn concurrency của các tác vụ bất đồng bộ trong flatMap.
- Kiểm soát số request đồng thời tới database hoặc HTTP service.
- Cấu hình consumer concurrency, poll records, pause/resume hoặc cơ chế điều tiết phù hợp của binder/client.
- Đặt timeout và giới hạn queue/buffer ở các ranh giới có thể tích lũy dữ liệu.
- Theo dõi consumer lag, thời gian xử lý và số request đang chờ.

Nếu một toán tử tạo buffer không giới hạn hoặc gọi dịch vụ ngoài với concurrency quá cao, việc dùng Flux không tự ngăn bộ nhớ tăng. Backpressure có ích khi cả nguồn, các toán tử và đích đều tuân thủ demand; nếu có thành phần không tuân thủ, cần chiến lược giới hạn riêng.

## 11. Kiểm thử reactive function

Có thể kiểm thử pipeline Reactor độc lập với Spring Context bằng StepVerifier:

~~~java
import java.util.function.Function;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class OrderFunctionTest {

    @Test
    void filtersInvalidEventsAndMapsValidOnes() {
        Function<Flux<OrderEvent>, Flux<OrderView>> function =
            events -> events
                .filter(event -> event.quantity() > 0)
                .map(event -> new OrderView(
                    event.orderId(),
                    event.quantity() >= 10 ? "BULK" : "NORMAL"
                ));

        StepVerifier.create(function.apply(Flux.just(
                new OrderEvent("A-1", 2),
                new OrderEvent("A-2", 12),
                new OrderEvent("A-3", 0)
            )))
            .expectNext(new OrderView("A-1", "NORMAL"))
            .expectNext(new OrderView("A-2", "BULK"))
            .verifyComplete();
    }
}
~~~

Các bài test nên kiểm tra:

1. Giá trị phát ra và thứ tự khi thứ tự là yêu cầu nghiệp vụ.
2. Luồng rỗng và trường hợp không có dữ liệu.
3. Lỗi được truyền, thay thế hoặc retry theo đúng chính sách.
4. Giới hạn concurrency của các tác vụ bất đồng bộ.
5. Cancellation và completion khi subscriber ngừng nhận dữ liệu.

Test Binder hữu ích để kiểm tra binding và chuyển đổi message của ứng dụng, nhưng không chứng minh binder message-channel đã hỗ trợ backpressure end-to-end. Để xác minh hành vi thực tế với Kafka, cần integration test dùng đúng binder, client, broker và phiên bản dự kiến triển khai.

## 12. Cách lựa chọn theo nhu cầu

| Nhu cầu | Hướng lựa chọn |
|---|---|
| Muốn dùng map/filter/flatMap để viết logic xử lý | Reactive function với Flux/Mono |
| Muốn dùng Spring Cloud Stream và Kafka theo cấu hình được duy trì | Kafka binder thông thường |
| Muốn dùng RabbitMQ với reactive function | Rabbit binder thông thường kết hợp Reactor trong function; không giả định có reactive transport |
| Muốn có backpressure xuyên suốt Kafka bằng Reactive Kafka Binder | Kiểm tra trạng thái release train trước; không chọn cho dự án mới vì binder đã deprecated/được loại bỏ ở một số train |
| Đang vận hành ứng dụng cũ dùng Reactive Kafka Binder | Kiểm tra artifact, phiên bản Reactor Kafka, thời hạn hỗ trợ và kế hoạch chuyển đổi |
| Cần xử lý bất đồng bộ có giới hạn | Dùng flatMap với concurrency phù hợp hoặc concatMap khi cần thứ tự |
| Cần retry theo từng message trong reactive pipeline | Dùng retryWhen/onErrorResume trong Reactor và bảo đảm idempotency |

Một quyết định kiến trúc cần dựa trên cả API function lẫn binder thực tế. Nếu mục tiêu chính là code xử lý dễ đọc và compose, reactive function có thể hữu ích ngay cả với binder thông thường. Nếu mục tiêu là backpressure từ broker đến consumer và ngược lại, phải kiểm tra khả năng của transport và trạng thái hỗ trợ của binder, không chỉ nhìn chữ ký Flux/Mono.

## 13. Checklist kiểm tra tình trạng hỗ trợ

Trước khi chọn Reactive Kafka Binder hoặc nâng cấp một ứng dụng đang dùng nó:

1. Ghi nhận phiên bản Spring Boot và Spring Cloud release train.
2. Đọc trang Reactive Kafka Binder trong tài liệu đúng phiên bản.
3. Đọc release notes của release train để tìm mục deprecated, removed hoặc migration.
4. Kiểm tra artifact spring-cloud-stream-binder-kafka-reactive có trong BOM và repository cho đúng version hay không.
5. Kiểm tra dependency tree để biết Reactor Kafka được kéo vào từ đâu.
6. Đọc thông báo chính thức về vòng đời Reactor Kafka.
7. Xác minh API acknowledgment, offset commit, retry và backpressure của đúng binder/version.
8. Chạy integration test với broker thật và đo hành vi tải.
9. Lập kế hoạch thay thế nếu binder hoặc dependency đã deprecated/removed.

Nguồn chính thức cần kiểm tra định kỳ:

- [Spring Cloud Stream - Reactive Functions support](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html): cách reactive function được gọi, giới hạn reactive Consumer và khác biệt khi dùng binder không reactive.
- [Spring Cloud Stream - Reactive Kafka Binder Overview](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-reactive-binder/overview.html): cảnh báo deprecated và trạng thái của binder trong tài liệu hiện hành.
- [Spring Cloud Stream - Reactive Kafka Binder Examples](https://docs.spring.io/spring-cloud-stream/reference/kafka/kafka-reactive-binder/examples.html): KafkaReceiver, KafkaSender, offset acknowledgment và ví dụ reactive.
- [Reactor Kafka Project Will Be Discontinued](https://spring.io/blog/2025/05/20/reactor-kafka-discontinued/): quyết định ngừng duy trì Reactor Kafka và deprecated các thành phần liên quan.
- [Spring Cloud 2025.1.0 Release Announcement](https://spring.io/blog/2025/11/25/spring-cloud-2025-1-0-aka-oakwood-has-been-released/): ghi chú artifact Reactive Kafka Binder bị loại khỏi release train.
- [Spring Cloud 2026.0.0 Release Announcement](https://spring.io/blog/2026/11/20/spring-cloud-2026-0-0-has-been-released/): thông tin release train hiện hành và ghi chú deprecation.
