# Giới hạn hỗ trợ kiểu bất đồng bộ hoặc reactive của từng aspect

Micrometer có các aspect cho annotation **@Timed**, **@Counted** và **@Observed** để tự động ghi nhận thời lượng, số lần thực thi hoặc Observation quanh một phương thức. Với phương thức đồng bộ, aspect có thể bắt đầu đo trước khi gọi phương thức và kết thúc khi phương thức trả về hoặc ném exception. Với phương thức bất đồng bộ, thời điểm phương thức trả về chưa chắc là lúc công việc hoàn tất. Vì vậy, cần hiểu kiểu dữ liệu trả về mà từng aspect nhận diện.

Trong các aspect chuẩn của Micrometer, **CompletionStage** là kiểu bất đồng bộ được hỗ trợ rõ ràng: Timer, Counter hoặc Observation được hoàn tất khi stage hoàn tất bình thường hoặc exceptional. **Future** thuần, Reactor **Mono**/**Flux** và Kotlin **suspend** không tự động có cùng semantics. Nếu aspect chỉ đo lúc phương thức tạo publisher hoặc trả về một future chưa được nhận diện, số liệu sẽ mô tả thời gian gọi phương thức thay vì thời gian xử lý thực tế.

Bài này thuộc module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**, tập trung vào giới hạn bất đồng bộ và reactive của **TimedAspect**, **CountedAspect** và **ObservedAspect**. Nội dung cũng hướng dẫn chọn cách instrument đúng lifecycle, tránh đo thiếu hoặc đếm sai, và kiểm thử hành vi hoàn tất, lỗi, hủy tác vụ.

## 1. Vì sao kiểu trả về quyết định thời điểm kết thúc đo?

Xét một phương thức trả về ngay một đối tượng đại diện cho công việc sẽ chạy sau đó:

~~~java
public CompletableFuture<Order> loadOrder(String id) {
    return CompletableFuture.supplyAsync(() -> repository.load(id));
}
~~~

Thời điểm phương thức loadOrder() trả về có thể chỉ cách thời điểm bắt đầu vài mili giây, trong khi truy vấn repository mất hàng trăm mili giây. Nếu aspect dừng Timer ngay khi phương thức trả về, metrics sẽ chỉ phản ánh thời gian tạo và trả future, không phải thời gian tải đơn hàng.

Để đo đúng, aspect cần biết rằng đối tượng trả về còn một lifecycle chưa kết thúc và có cách đăng ký callback khi lifecycle đó hoàn tất. **CompletionStage** cung cấp callback whenComplete(), nên Micrometer có thể dừng phép đo ở thời điểm completion. Các aspect chuẩn kiểm tra kiểu trả về khai báo của phương thức để quyết định có chờ stage hay không.

Đây là khác biệt giữa hai mốc:

- **Method return**: mã phương thức đã trả về đối tượng đại diện cho công việc.
- **Async completion**: công việc đã hoàn tất, thất bại hoặc kết thúc theo lifecycle được hỗ trợ.

Không phải mọi kiểu đại diện cho công việc bất đồng bộ đều có API completion tương thích với aspect của Micrometer.

## 2. CompletionStage được hỗ trợ bởi ba aspect

Các aspect chuẩn hiện hành xử lý CompletionStage theo cách sau:

| Aspect | Mục đích | Khi phương thức trả CompletionStage |
|---|---|---|
| TimedAspect | Ghi thời lượng bằng Timer hoặc LongTaskTimer | Dừng Timer khi stage hoàn tất; lỗi bất đồng bộ được ghi nhận cùng tag exception |
| CountedAspect | Đếm lần thực thi và kết quả | Tăng Counter khi stage hoàn tất; stage thất bại được phân loại là failure |
| ObservedAspect | Tạo Observation để nối metrics, tracing hoặc handler khác | Dừng Observation khi stage hoàn tất; lỗi được đưa vào Observation |

CompletableFuture triển khai CompletionStage nên được hỗ trợ. Kiểu khai báo trả về cũng quan trọng: nên khai báo CompletionStage<T> hoặc CompletableFuture<T> trực tiếp. Nếu phương thức khai báo trả về Future<T> nhưng lúc chạy lại trả một CompletableFuture, aspect không nhất thiết nhận ra vì nó kiểm tra kiểu trả về của method.

### Ví dụ @Timed với @Async

~~~java
import java.util.concurrent.CompletableFuture;

import io.micrometer.core.annotation.Timed;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class InvoiceService {

    @Async
    @Timed(value = "invoice.generate")
    public CompletableFuture<Invoice> generate(String orderId) {
        Invoice invoice = createInvoice(orderId);
        return CompletableFuture.completedFuture(invoice);
    }

    private Invoice createInvoice(String orderId) {
        // Tạo hóa đơn hoặc gọi dịch vụ bên ngoài.
        return new Invoice(orderId);
    }
}
~~~

Với kiểu trả về được hỗ trợ, Timer được ghi khi CompletableFuture hoàn tất, kể cả khi hoàn tất exceptional. Thời lượng bao gồm khoảng chờ từ lúc bắt đầu đến lúc stage hoàn tất, không chỉ thời gian chạy đoạn mã tạo future.

Trong ứng dụng Spring, @Async cần được bật và phương thức phải được gọi qua Spring proxy. Nếu phương thức trả về void, caller không nhận được một CompletionStage để aspect chờ. Khi đó, không nên mặc định Timer bên ngoài sẽ đo đến lúc tác vụ nền hoàn tất; hãy trả về CompletableFuture/CompletionStage hoặc instrument trực tiếp bên trong tác vụ.

## 3. Cấu hình các aspect trong Spring

Nếu tự cấu hình aspect của Micrometer, có thể đăng ký bean như sau:

~~~java
import io.micrometer.core.aop.CountedAspect;
import io.micrometer.core.aop.TimedAspect;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.aop.ObservedAspect;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class MetricsAspectConfiguration {

    @Bean
    TimedAspect timedAspect(MeterRegistry registry) {
        return new TimedAspect(registry);
    }

    @Bean
    CountedAspect countedAspect(MeterRegistry registry) {
        return new CountedAspect(registry);
    }

    @Bean
    ObservedAspect observedAspect(ObservationRegistry registry) {
        return new ObservedAspect(registry);
    }
}
~~~

Các aspect này cần AOP được kích hoạt và đối tượng mục tiêu phải được gọi qua proxy hoặc cơ chế weaving tương ứng. Chỉ thêm annotation vào method không đảm bảo aspect sẽ chạy. Micrometer Spring Boot không tự áp dụng @Timed cho mọi method service tùy ý; có thể đăng ký TimedAspect/CountedAspect rõ ràng như ví dụ. Các phiên bản Spring Boot có hỗ trợ annotation scanning cũng có thể bật thuộc tính management.observations.annotations.enabled=true cùng dependency AOP phù hợp; hãy kiểm tra tài liệu đúng phiên bản để tránh cấu hình cả hai đường instrument.

Không bật đồng thời nhiều cơ chế instrument cùng một method nếu không có chủ đích. Ví dụ, một HTTP controller có thể đã được Spring Boot instrument tự động; thêm @Observed hoặc @Timed và một aspect riêng có thể tạo Observation hoặc Timer trùng lặp. Chọn một nơi chịu trách nhiệm đo cho mỗi ranh giới nghiệp vụ.

## 4. Giới hạn riêng của @Timed và TimedAspect

TimedAspect đo phương thức đồng bộ từ lúc bắt đầu intercept đến lúc method kết thúc. Với method trả về CompletionStage, aspect gắn callback để dừng Timer khi stage hoàn tất. Nó không tự theo dõi mọi loại async handle.

Các trường hợp cần lưu ý:

- Method trả CompletableFuture<T> hoặc CompletionStage<T>: aspect có thể chờ completion.
- Method trả Future<T> thuần: không có callback whenComplete() trong contract của CompletionStage; aspect không có semantics chờ completion tương tự.
- Method trả Mono<T> hoặc Flux<T>: publisher thường lazy; method trả về publisher trước khi subscription và xử lý dữ liệu bắt đầu. TimedAspect sẽ đo lời gọi tạo publisher, không phải toàn bộ stream.
- Method trả void nhưng gửi công việc sang executor: aspect chỉ có thể đo phạm vi method mà nó intercept; không thể suy ra khi nào tác vụ nền hoàn tất.

Với @Timed(longTask = true), aspect dùng LongTaskTimer nhưng vẫn cần biết lifecycle nào đánh dấu kết thúc. LongTaskTimer không tự giải quyết giới hạn của kiểu trả về; với CompletionStage, nó được dừng khi stage hoàn tất, còn Publisher vẫn cần instrumentation reactive riêng.

## 5. Giới hạn riêng của @Counted và CountedAspect

CountedAspect đếm kết quả thực thi. Mặc định, aspect ghi nhận cả thành công và thất bại. Có thể cấu hình recordFailuresOnly = true nếu chỉ quan tâm số lần lỗi.

~~~java
import io.micrometer.core.annotation.Counted;
import org.springframework.stereotype.Service;

@Service
public class PaymentService {

    @Counted(value = "payment.authorize")
    public AuthorizationResult authorize(PaymentRequest request) {
        return gateway.authorize(request);
    }

    @Counted(
            value = "payment.reconciliation",
            recordFailuresOnly = true
    )
    public void reconcile(String batchId) {
        reconciliationJob.run(batchId);
    }
}
~~~

Với phương thức đồng bộ, aspect ghi nhận khi method trả về hoặc ném exception. Với CompletionStage, nó chờ stage hoàn tất rồi mới tăng Counter; kết quả exceptional được phân loại failure. Điều này giúp số đếm phản ánh kết quả cuối của tác vụ bất đồng bộ.

Với Mono hoặc Flux, method có thể trả publisher thành công trước khi có subscription. CountedAspect không tự đợi publisher complete/error. Counter khi đó có thể đếm số lần tạo pipeline thay vì số lần pipeline được subscribe, hoàn tất hoặc thất bại. Hai câu hỏi này khác nhau và cần meter riêng nếu đều có ý nghĩa.

Nếu muốn đếm số lần subscription hoặc kết quả của stream, hãy đặt Counter trong reactive pipeline bằng các operator tương ứng, hoặc dùng reactor-core-micrometer để instrument stream.

## 6. Giới hạn riêng của @Observed và ObservedAspect

@Observed tạo Observation. Tùy các ObservationHandler được đăng ký, Observation có thể tạo Timer, span, log hoặc nhiều loại tín hiệu cùng lúc.

Với method trả CompletionStage, ObservedAspect giữ Observation đến khi stage hoàn tất và đánh dấu lỗi nếu stage hoàn tất exceptional. Tuy nhiên, scope hiện hành của Observation chỉ được mở quanh lời gọi method ban đầu; việc giữ Observation chưa đồng nghĩa ThreadLocal context tự động được mở trên mọi thread hoàn tất stage.

Ví dụ:

~~~java
import java.util.concurrent.CompletableFuture;

import io.micrometer.observation.annotation.Observed;
import org.springframework.stereotype.Service;

@Service
public class RiskService {

    @Observed(
            name = "risk.assessment",
            contextualName = "risk-assessment"
    )
    public CompletableFuture<RiskResult> assess(Transaction transaction) {
        return CompletableFuture.supplyAsync(
                () -> runRiskRules(transaction)
        );
    }

    private RiskResult runRiskRules(Transaction transaction) {
        return new RiskResult();
    }
}
~~~

Observation có thể được dừng khi future hoàn tất. Nếu code bên trong supplyAsync() cần truy cập trace hoặc Observation context, phải cấu hình context propagation phù hợp với executor/tracing stack. Không nên giả định scope của thread gọi ban đầu tự động tồn tại trong thread worker.

Với Publisher, ObservedAspect cũng không tự giữ Observation cho đến onComplete(), onError() hoặc cancellation. Phương thức trả Mono/Flux ngay khi dựng pipeline; aspect kết thúc Observation quanh lời gọi đó. Dùng cơ chế Observation dành cho Reactor hoặc đặt lifecycle Observation trong pipeline nếu muốn đo toàn bộ thời gian reactive.

## 7. Future, CompletionStage và Publisher không tương đương

| Kiểu trả về | Có callback completion chuẩn? | Aspect chuẩn tự chờ? | Hướng xử lý |
|---|---|---|---|
| Kiểu đồng bộ (T, void) | Không cần | Có, đến khi method return/throw | Dùng aspect thông thường |
| CompletionStage<T> | Có whenComplete() | Có | Phù hợp cho @Timed, @Counted, @Observed |
| CompletableFuture<T> | Có, triển khai CompletionStage | Có | Được hỗ trợ như CompletionStage |
| Future<T> thuần | Không có callback trong interface | Không | Tự gắn callback ở implementation cụ thể hoặc instrument trong task |
| Reactor Mono<T> / Flux<T> | Có signal lifecycle của Publisher | Không | Dùng Reactor Micrometer hoặc operator |
| RxJava Single / Observable | Có callback riêng của thư viện | Không | Dùng integration/operator của RxJava |
| Kotlin suspend | Không được khai báo là CompletionStage | Không thể mặc định | Dùng hỗ trợ coroutine/framework hoặc instrument trong coroutine |

Điểm quan trọng là aspect kiểm tra kiểu trả về mà nó hiểu, không thể tự suy luận semantics của mọi thư viện bất đồng bộ. Việc một kiểu có thể hoàn tất trong tương lai không có nghĩa nó tương thích với CompletionStage.

## 8. Vì sao Mono và Flux cần đo ở subscription lifecycle?

Reactor sử dụng mô hình lazy. Khi gọi một service method trả Mono, thường chỉ có một pipeline được tạo. Công việc thực tế bắt đầu khi có subscriber và kết thúc khi stream phát terminal signal: complete, error hoặc cancel.

~~~java
public Mono<Order> findOrder(String id) {
    return repository.findById(id)
            .map(this::enrich);
}
~~~

Nếu đặt @Timed ở method trên và dùng TimedAspect, thời gian có thể chỉ bao gồm việc dựng pipeline. Nó không bao gồm thời gian database query và các operator chạy sau subscription.

Lifecycle cần quan sát:

~~~text
Gọi method
   |
   v
Tạo Mono/Flux ----------------------> trả Publisher
                                         |
                                      subscribe
                                         |
                                   xử lý các operator
                                         |
                       +-----------------+-----------------+
                       |                 |                 |
                    complete           error             cancel
                       |                 |                 |
                       +-------- kết thúc lifecycle -------+
~~~

Instrumentation reactive cần gắn với subscription để đo đúng thời gian xử lý, đồng thời xử lý đủ cả complete, error và cancel.

## 9. Dùng reactor-core-micrometer cho reactive pipeline

Reactor cung cấp module reactor-core-micrometer với các operator Micrometer.metrics() và Micrometer.observation(). Cần thêm dependency tương thích với phiên bản Reactor đang sử dụng và truyền registry phù hợp.

Ví dụ ghi metrics cho một Flux:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Micrometer;

import io.micrometer.core.instrument.MeterRegistry;

public class EventStreamMetrics {
    private final MeterRegistry registry;

    public EventStreamMetrics(MeterRegistry registry) {
        this.registry = registry;
    }

    public Flux<Event> observe(Flux<Event> source) {
        return source
                .name("events.process")
                .tag("source", "kafka")
                .tap(Micrometer.metrics(registry));
    }
}
~~~

name() đặt tiền tố metric của pipeline; tag() bổ sung chiều phân loại có cardinality thấp; tap(Micrometer.metrics(registry)) gắn listener thu thập metrics vào lifecycle của stream.

Nếu cần Observation thay vì chỉ metrics:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Micrometer;

import io.micrometer.observation.ObservationRegistry;

public class EventStreamObservation {
    private final ObservationRegistry observationRegistry;

    public EventStreamObservation(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    public Flux<Event> observe(Flux<Event> source) {
        return source
                .name("events.process")
                .tap(Micrometer.observation(observationRegistry));
    }
}
~~~

Observation có thể được chuyển thành metrics, trace hoặc handler khác tùy cấu hình registry. Đây là cách tích hợp ở tầng reactive thay vì mong ObservedAspect hiểu Publisher.

## 10. Tự đo Mono hoặc Flux bằng Timer.Sample và doFinally

Khi cần metric riêng hoặc tag phụ thuộc terminal signal, có thể đặt Timer trực tiếp trong pipeline. Dùng Mono.defer() để tạo sample cho mỗi subscription; nếu tạo sample khi dựng pipeline, thời gian chờ trước subscription cũng có thể bị tính nhầm.

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.Timer.Sample;
import reactor.core.publisher.Mono;
import reactor.core.publisher.SignalType;
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public class CatalogMetrics {
    private final MeterRegistry registry;
    private final ReactiveCrudRepository<Product, String> repository;
    private final Timer successTimer;
    private final Timer errorTimer;
    private final Timer cancelledTimer;

    public CatalogMetrics(
            MeterRegistry registry,
            ReactiveCrudRepository<Product, String> repository) {
        this.registry = registry;
        this.repository = repository;
        this.successTimer = registry.timer(
                "catalog.lookup", "outcome", "success");
        this.errorTimer = registry.timer(
                "catalog.lookup", "outcome", "error");
        this.cancelledTimer = registry.timer(
                "catalog.lookup", "outcome", "cancelled");
    }

    public Mono<Product> lookup(String id) {
        return Mono.defer(() -> {
            Sample sample = Timer.start(registry);

            return repository.findById(id)
                    .doFinally(signal -> sample.stop(timerFor(signal)));
        });
    }

    private Timer timerFor(SignalType signal) {
        return switch (signal) {
            case ON_COMPLETE -> successTimer;
            case ON_ERROR -> errorTimer;
            case CANCEL -> cancelledTimer;
            default -> cancelledTimer;
        };
    }
}
~~~

Ví dụ dùng doFinally() để dừng sample cho complete, error và cancel. Trong code thực tế, có thể đơn giản hóa các terminal signal hoặc dùng tag có tập giá trị cố định. Không dùng message exception, request ID hoặc user ID làm tag.

Với Flux, cách này đo toàn bộ subscription. Nếu cần đo từng phần tử hoặc từng lần gọi downstream, đặt Timer ở đúng operator tương ứng. Đặt instrumentation trước hay sau retry() cũng làm thay đổi ý nghĩa:

- Instrument bên trong vùng được retry: mỗi attempt có một phép đo.
- Instrument bên ngoài toàn bộ vùng retry: một phép đo bao gồm tổng thời gian của các attempt và khoảng chờ retry.

Chọn vị trí theo câu hỏi vận hành cần trả lời.

## 11. Cancellation và lỗi cần được tính riêng

Một reactive stream có thể kết thúc theo nhiều cách:

- Complete: stream kết thúc bình thường.
- Error: stream kết thúc do exception.
- Cancel: subscriber hủy việc tiêu thụ trước khi stream hoàn tất.

Nếu chỉ ghi nhận doOnSuccess hoặc doOnComplete, có thể bỏ sót lỗi hoặc cancellation. doFinally() nhận được terminal signal cho cả ba trường hợp và thường phù hợp để kết thúc Timer tổng thể.

Cancellation không nhất thiết là lỗi ứng dụng. Ví dụ client đóng kết nối hoặc người dùng rời trang có thể làm stream bị hủy. Hãy giữ outcome riêng để dashboard không gộp cancellation vào success hoặc error nếu hai trường hợp có ý nghĩa vận hành khác nhau.

Với CompletionStage, cancellation thường biểu hiện qua trạng thái exceptional/cancelled của stage và được callback completion nhận diện như một completion có lỗi. Nếu cần phân biệt cancellation với exception thông thường, kiểm tra exception và thiết kế tag outcome phù hợp.

## 12. Kotlin coroutine và các kiểu async khác

Kotlin suspend function không khai báo trả về CompletionStage. Ở bytecode JVM, coroutine sử dụng Continuation và cơ chế state machine; phương thức có thể trả về trước khi coroutine hoàn tất. Vì vậy, không nên mặc định TimedAspect, CountedAspect hoặc ObservedAspect sẽ giữ phép đo đến lúc coroutine kết thúc.

Với coroutine, chọn một integration hỗ trợ coroutine/context propagation của framework đang dùng hoặc instrument trực tiếp trong coroutine bằng API phù hợp. Cần bảo đảm phép đo kết thúc trong finally để bao gồm cả lỗi và cancellation.

Tương tự, RxJava Single, Maybe, Observable và các reactive type khác có lifecycle riêng. Chọn operator hoặc bridge của thư viện để đo subscribe, completion, error và cancellation/disposal. Không ép các kiểu này qua một cast sang CompletionStage chỉ để aspect nhận diện.

## 13. AOP proxy cũng là một giới hạn độc lập

Ngay cả khi kiểu trả về được hỗ trợ, aspect chỉ chạy nếu lời gọi đi qua proxy hoặc được AspectJ weaving.

Các trường hợp thường làm annotation không có tác dụng:

- Một method trong cùng object gọi trực tiếp method khác của chính object đó (self-invocation), bỏ qua Spring proxy.
- Object được tạo bằng new thay vì được Spring quản lý.
- AOP dependency hoặc aspect bean chưa được cấu hình.
- Kiểu proxy không thể intercept method/class theo visibility hoặc final modifier đang dùng.
- Method đã được framework instrument tự động, đồng thời lại bị aspect instrument lần nữa.

Vì vậy, khi metrics không xuất hiện, kiểm tra cả hai lớp: aspect có intercept method không và aspect có hiểu lifecycle của kiểu trả về không. Hai vấn đề này khác nhau và cần cách xử lý khác nhau.

## 14. Kiểm thử async và reactive đúng lifecycle

Không nên chỉ kiểm tra rằng phương thức trả về future hoặc publisher mà kết luận Timer đã đo đúng. Test cần kiểm tra trước và sau completion.

### Kiểm thử CompletionStage

Tạo một future chưa hoàn tất để kiểm tra Timer/Counter/Observation chưa được ghi kết quả cuối trước khi stage complete:

~~~java
CompletableFuture<String> pending = new CompletableFuture<>();

CompletableFuture<String> result = service.processAsync(pending);

assertThat(timer.count()).isZero();

pending.complete("done");

assertThat(result.join()).isEqualTo("done");
assertThat(timer.count()).isEqualTo(1);
~~~

Đây là ý tưởng kiểm thử; service phải được gọi qua proxy có TimedAspect và Timer phải là meter tương ứng. Bổ sung một test hoàn tất exceptional để xác nhận exception tag hoặc failure counter được ghi đúng.

### Kiểm thử Reactor

Dùng StepVerifier để điều khiển subscription và terminal signal:

~~~java
StepVerifier.create(service.lookup("P-100"))
        .expectNextMatches(product -> product.id().equals("P-100"))
        .verifyComplete();

assertThat(registry.get("catalog.lookup")
        .tag("outcome", "success")
        .timer()
        .count()).isEqualTo(1);
~~~

Bổ sung các test:

- Publisher phát error: Timer ghi outcome error.
- Subscriber cancel: Timer ghi outcome cancelled.
- Publisher chưa subscribe: chưa tạo sample nếu dùng Mono.defer().
- Publisher được subscribe hai lần: có hai phép đo nếu mỗi subscription là một lần thực thi.
- Retry: xác nhận phép đo nằm trong hay ngoài vùng retry đúng với semantics mong muốn.

### Kiểm thử AOP proxy

Dùng Spring context test hoặc AspectJProxyFactory để xác nhận method thực sự được intercept. Một unit test gọi trực tiếp object chưa proxy không kiểm tra được AOP.

## 15. Chọn cách instrument theo loại công việc

| Công việc | Cách phù hợp |
|---|---|
| Phương thức đồng bộ | @Timed, @Counted, @Observed qua aspect hoặc API thủ công |
| CompletableFuture/CompletionStage | Aspect chuẩn có thể chờ completion |
| Future thuần | Instrument trong task hoặc nối callback qua implementation cụ thể |
| Reactor Mono/Flux | reactor-core-micrometer hoặc doFinally/Observation trong pipeline |
| Kotlin coroutine | Coroutine-aware instrumentation và context propagation |
| @Async void | Instrument trong worker task hoặc đổi sang trả CompletionStage để theo dõi completion |
| WebFlux server request | Ưu tiên Observation tự động của framework cho lifecycle HTTP; tránh tạo instrumentation trùng |

## 16. Checklist trước khi dùng annotation trên async/reactive method

Trước khi áp dụng aspect, hãy xác nhận:

- Method được gọi qua Spring proxy hoặc AspectJ weaving.
- Aspect tương ứng đã được đăng ký và dùng đúng registry.
- Kiểu trả về được khai báo là CompletionStage nếu muốn aspect chờ completion.
- Không nhầm Future thuần hoặc Publisher với CompletionStage.
- Mono/Flux được instrument ở subscription lifecycle.
- Completion, error và cancellation được xử lý theo semantics mong muốn.
- Context propagation được cấu hình nếu async task cần trace/Observation context.
- Không instrument trùng với HTTP, database hoặc framework observation đã có.
- Tag có cardinality thấp và không chứa ID duy nhất.
- Test xác nhận thời điểm ghi metric trước/sau completion, error và cancel.

Các aspect của Micrometer giúp instrument phương thức đồng bộ và CompletionStage thuận tiện. Chúng không tự hiểu lifecycle của mọi abstraction bất đồng bộ. Với reactive Publisher và coroutine, phép đo phải gắn vào lifecycle thực thi của thư viện đó. Khi chọn đúng ranh giới bắt đầu/kết thúc, xử lý cả lỗi và cancellation, đồng thời kiểm tra proxy và context propagation, metrics mới phản ánh thời gian và kết quả công việc thực sự.

## Tài liệu tham khảo

- [Micrometer Timers và TimedAspect](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer Counters và CountedAspect](https://docs.micrometer.io/micrometer/reference/concepts/counters.html)
- [Micrometer Observation Components và ObservedAspect](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Spring Boot Observability và annotation scanning](https://docs.spring.io/spring-boot/reference/actuator/observability.html)
- [Project Reactor - Publisher metrics và Observation](https://projectreactor.io/docs/core/release/reference/metrics.html)
- [Micrometer TimedAspect source](https://github.com/micrometer-metrics/micrometer/blob/main/micrometer-core/src/main/java/io/micrometer/core/aop/TimedAspect.java)
- [Micrometer CountedAspect source](https://github.com/micrometer-metrics/micrometer/blob/main/micrometer-core/src/main/java/io/micrometer/core/aop/CountedAspect.java)
- [Micrometer ObservedAspect source](https://github.com/micrometer-metrics/micrometer/blob/main/micrometer-observation/src/main/java/io/micrometer/observation/aop/ObservedAspect.java)
