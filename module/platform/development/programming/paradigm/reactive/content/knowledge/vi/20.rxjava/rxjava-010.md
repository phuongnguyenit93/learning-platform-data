# RxJava

## Lựa chọn Reactor hoặc RxJava theo môi trường tích hợp

Trong Java, Project Reactor và RxJava đều cung cấp cách xây dựng pipeline bất đồng bộ bằng các toán tử như **map**, **filter**, **flatMap**, **zip** và các cơ chế xử lý lỗi. Cả hai có thể dùng để biểu diễn luồng dữ liệu theo thời gian, kết hợp nhiều tác vụ I/O và điều phối công việc qua scheduler. Tuy nhiên, chúng có hệ kiểu dữ liệu, hợp đồng tiêu thụ và hệ sinh thái tích hợp khác nhau.

Lựa chọn phù hợp phụ thuộc trước hết vào môi trường ứng dụng và các API mà ứng dụng đang dùng. Một dịch vụ Spring WebFlux hoặc Spring Data reactive thường thuận lợi khi dùng Reactor làm mô hình chính vì các API của hệ sinh thái này sử dụng **Mono** và **Flux**. Một ứng dụng đã dùng RxJava rộng rãi, hoặc một thư viện tích hợp trả về các kiểu RxJava, có thể tiếp tục dùng RxJava để tránh chuyển đổi không cần thiết. Khi hai hệ sinh thái cùng xuất hiện, nên đặt ranh giới chuyển đổi rõ ràng và giữ một mô hình reactive nhất quán trong từng phần của ứng dụng.

### 1. Hai thư viện cùng tư duy toán tử nhưng không cùng một API

Reactor và RxJava cùng cho phép mô tả chuỗi biến đổi dữ liệu. Một pipeline thường gồm nguồn, các toán tử trung gian và một subscriber cuối:

~~~text
Nguồn dữ liệu
    |
    v
map / filter / flatMap
    |
    v
Điều phối, xử lý lỗi, giới hạn nhu cầu
    |
    v
Subscriber hoặc thành phần tích hợp
~~~

Tên toán tử tương tự không có nghĩa mọi chi tiết đều giống nhau. Kiểu trả về, cách biểu diễn luồng rỗng, backpressure, scheduler mặc định, context, kiểm thử và vòng đời subscription có thể khác. Khi chuyển mã giữa hai thư viện, cần kiểm tra ngữ nghĩa của từng API thay vì chỉ thay tên lớp hoặc tên toán tử.

| Khía cạnh | Project Reactor | RxJava |
| --- | --- | --- |
| Các kiểu luồng chính | **Mono<T>**, **Flux<T>** | **Single<T>**, **Maybe<T>**, **Completable**, **Flowable<T>**, **Observable<T>** |
| Hợp đồng Reactive Streams | **Mono** và **Flux** triển khai **Publisher** | **Flowable** triển khai **Publisher**; **Observable** không dùng giao thức demand của Reactive Streams |
| Scheduler | **Schedulers** của Reactor | **Schedulers** của RxJava; RxAndroid bổ sung tích hợp cho Android |
| Kiểm thử | **StepVerifier**, **reactor-test** | **TestObserver**, **TestSubscriber**, **TestScheduler** |
| Tích hợp Spring reactive | Kiểu native phổ biến là **Mono** và **Flux** | Có thể tích hợp qua adapter, nhưng không phải kiểu API mặc định của Spring WebFlux |

### 2. Bắt đầu từ môi trường tích hợp

Nếu ứng dụng xây dựng trên Spring WebFlux, Reactor thường là lựa chọn tự nhiên. Controller có thể trả về **Mono<Response>** cho một kết quả hoặc **Flux<Event>** cho một luồng nhiều phần tử. Các repository reactive của Spring Data như R2DBC cũng thường sử dụng **Mono** và **Flux**, nên dữ liệu có thể đi qua các tầng mà không cần chuyển kiểu ở mỗi ranh giới.

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
class OrderController {
    private final OrderService orderService;

    OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @GetMapping("/orders")
    Flux<OrderView> listOrders() {
        return orderService.findAll();
    }

    @GetMapping("/orders/featured")
    Mono<OrderView> featuredOrder() {
        return orderService.findFeatured();
    }
}
~~~

Trong trường hợp này, dùng Reactor xuyên suốt tầng web, service và repository giúp giữ nguyên kiểu dữ liệu, cách truyền lỗi và cơ chế backpressure. Nếu một thư viện ngoài trả về RxJava, chỉ cần chuyển đổi tại adapter tích hợp thay vì làm mọi tầng phải biết cả hai hệ kiểu.

RxJava phù hợp khi dự án đã chuẩn hóa trên RxJava hoặc các thành phần cốt lõi trả về các kiểu RxJava. RxJava được dùng trong nhiều loại ứng dụng Java, bao gồm ứng dụng Android, client và dịch vụ backend. Nếu một ứng dụng đang dùng **Flowable**, **Observable**, **Single** và các công cụ kiểm thử RxJava, tiếp tục dùng thư viện đó thường giảm chi phí học lại và chuyển đổi.

Không nên chọn thư viện chỉ vì một toán tử có tên quen thuộc hoặc vì một ví dụ trên mạng dùng thư viện đó. Hãy xem kiểu dữ liệu mà framework, driver, SDK và các thư viện hiện có trả về; đó thường là tín hiệu rõ nhất về chi phí tích hợp.

Khi tích hợp RxJava, cần xác định rõ major version mà các thư viện đang dùng. RxJava 2 và RxJava 3 có namespace package khác nhau, nên các kiểu cùng tên ở hai phiên bản không thể truyền trực tiếp cho nhau. Hãy chọn phiên bản tương thích với SDK và plugin hiện có, đồng thời tránh để nhiều major version xuất hiện xuyên suốt API của cùng một module.

### 3. Hiểu đúng các kiểu dữ liệu trước khi chọn

Điểm khác biệt quan trọng nằm ở cách biểu diễn số lượng phần tử:

| Nhu cầu | Reactor | RxJava | Ý nghĩa |
| --- | --- | --- | --- |
| Không hoặc một phần tử | **Mono<T>** | **Maybe<T>** | Có thể phát một giá trị hoặc hoàn tất rỗng |
| Chính xác một phần tử | Không có kiểu riêng; dùng **Mono<T>** và xác định hợp đồng | **Single<T>** | Phải phát một giá trị hoặc kết thúc bằng lỗi |
| Không phát giá trị, chỉ báo hoàn tất | Thường dùng **Mono<Void>** | **Completable** | Biểu diễn một tác vụ chỉ quan tâm thành công hoặc lỗi |
| Không hoặc nhiều phần tử, có backpressure | **Flux<T>** | **Flowable<T>** | Consumer có thể điều khiển demand theo Reactive Streams |
| Không hoặc nhiều phần tử, không có demand protocol | Không có kiểu tương đương trực tiếp; thường dùng **Flux<T>** | **Observable<T>** | Luồng sự kiện không có cơ chế **request(n)** của Reactive Streams |

**Mono<T>** có thể hoàn tất rỗng, nên không hoàn toàn tương đương với **Single<T>**. Khi chuyển từ Mono sang Single, cần quyết định điều gì xảy ra nếu Mono không phát giá trị. RxJava Single phải phát đúng một giá trị hoặc lỗi; nó không thể biểu diễn completion rỗng như **Mono.empty()**.

Tương tự, **Mono<Void>** thường gần với **Completable** về ý nghĩa tác vụ không phát dữ liệu. Với luồng nhiều phần tử, **Flux<T>** gần với **Flowable<T>** hơn khi cần tuân theo Reactive Streams. **Observable<T>** có thể phù hợp cho sự kiện không cần backpressure, nhưng không nên xem nó là thay thế tương đương cho một Flux có kiểm soát demand.

### 4. Backpressure: phân biệt Flowable và Observable

Reactor **Flux** và RxJava **Flowable** tham gia hợp đồng Reactive Streams. Subscriber yêu cầu số phần tử muốn nhận qua **request(n)**, và Publisher phải tuân theo demand. Đây là nền tảng để điều tiết luồng khi consumer xử lý chậm.

RxJava **Observable** không có giao thức demand **request(n)**. Nó phát tín hiệu theo mô hình push; nếu nguồn phát nhanh hơn consumer, ứng dụng cần tự chọn cách điều tiết phù hợp, chẳng hạn buffer, sample, debounce hoặc drop theo yêu cầu nghiệp vụ. Những toán tử này xử lý tốc độ theo cách riêng nhưng không biến Observable thành Publisher có backpressure.

Ví dụ giữ giá trị mới nhất khi consumer chỉ cần trạng thái hiện tại:

~~~java
import reactor.core.publisher.Flux;

Flux<PriceTick> latestReactorPrices =
    priceFeed.events()
        .onBackpressureLatest();
~~~

RxJava **Flowable** có toán tử tương tự:

~~~java
import io.reactivex.rxjava3.core.Flowable;

Flowable<PriceTick> latestRxPrices =
    rxPriceFeed.events()
        .onBackpressureLatest();
~~~

Chính sách latest bỏ qua các giá trị cũ đang chờ để ưu tiên giá trị mới nhất. Nó phù hợp cho một số màn hình hiển thị trạng thái hoặc dữ liệu đo liên tục, nhưng không phù hợp với sự kiện mà mỗi phần tử đều quan trọng như thanh toán, ghi nhận đơn hàng hoặc thay đổi tồn kho.

Với sự kiện cần được xử lý đầy đủ, hãy chọn buffer có giới hạn, lưu trữ bền vững hoặc cơ chế xác nhận và đọc lại từ nguồn. Không dùng buffer không giới hạn như một giải pháp mặc định: nếu producer liên tục nhanh hơn consumer, hàng đợi có thể tăng đến khi cạn bộ nhớ.

### 5. Scheduler và điều phối thread

Hai thư viện đều cung cấp scheduler, nhưng tên gọi và chi tiết vận hành không nên được xem là hoàn toàn tương đương.

| Loại công việc | Reactor | RxJava |
| --- | --- | --- |
| Công việc tính toán ngắn | **Schedulers.parallel()** | **Schedulers.computation()** |
| Tích hợp API blocking | **Schedulers.boundedElastic()** | **Schedulers.io()** hoặc scheduler được cấu hình phù hợp |
| Tuần tự hóa trên một thread | **Schedulers.single()** | **Schedulers.single()** |
| Kiểm thử thời gian | **VirtualTimeScheduler** / **withVirtualTime** | **TestScheduler** |

Trong Reactor, **subscribeOn** điều phối quá trình đăng ký nguồn và request upstream; **publishOn** chuyển việc xử lý tín hiệu downstream sau vị trí đặt toán tử sang scheduler được chọn. RxJava có **subscribeOn** và **observeOn** với vai trò gần tương ứng: subscribeOn điều phối subscription đến nguồn, còn observeOn chuyển các tín hiệu phía sau sang scheduler được chọn.

Ví dụ Reactor:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

Mono<Customer> customer =
    Mono.fromCallable(() -> legacyRepository.findCustomer(customerId))
        .subscribeOn(Schedulers.boundedElastic())
        .publishOn(Schedulers.parallel())
        .map(this::toCustomerView);
~~~

Ví dụ RxJava 3:

~~~java
import io.reactivex.rxjava3.core.Single;

Single<Customer> customer =
    Single.fromCallable(() -> legacyRepository.findCustomer(customerId))
        .subscribeOn(io.reactivex.rxjava3.schedulers.Schedulers.io())
        .observeOn(io.reactivex.rxjava3.schedulers.Schedulers.computation())
        .map(this::toCustomerView);
~~~

Hai ví dụ cùng trì hoãn lời gọi blocking và chuyển phần biến đổi phía sau sang scheduler tính toán. Tuy nhiên, scheduler cụ thể, chính sách quản lý thread và khả năng cấu hình của từng thư viện khác nhau. Hãy đọc tài liệu của phiên bản đang dùng và đo đạc dưới tải thật; không thay máy móc **boundedElastic** bằng **io** hoặc **parallel** bằng **computation** mà không xét đặc tính công việc.

### 6. Xử lý lỗi cũng cần được đối chiếu theo ngữ nghĩa

Reactor dùng các toán tử như **onErrorReturn**, **onErrorResume** và **retryWhen**. RxJava có các toán tử như **onErrorReturnItem**, **onErrorResumeNext** và **retryWhen**. Tên và overload có thể khác nhau, đồng thời chính sách retry và kiểu trả về cũng cần được kiểm tra.

Ví dụ phục hồi một lỗi tra cứu trong Reactor:

~~~java
import reactor.core.publisher.Mono;

Mono<Profile> profile =
    profileClient.findProfile(userId)
        .onErrorResume(
            ProfileUnavailableException.class,
            error -> cachedProfile(userId)
        );
~~~

Ví dụ tương tự trong RxJava:

~~~java
import io.reactivex.rxjava3.core.Maybe;

Maybe<Profile> profile =
    rxProfileClient.findProfile(userId)
        .onErrorResumeNext(error -> {
            if (error instanceof ProfileUnavailableException) {
                return cachedProfileRx(userId);
            }
            return Maybe.error(error);
        });
~~~

Hai ví dụ thể hiện cùng ý định nghiệp vụ: chỉ dùng cache dự phòng cho loại lỗi đã xác định. Không nên chuyển mọi lỗi thành giá trị rỗng nếu điều đó khiến lỗi xác thực, lỗi dữ liệu hoặc lỗi hệ thống bị che giấu.

Khi chuyển pipeline giữa hai thư viện, hãy kiểm tra:

- Lỗi được phát ngay hay được trì hoãn khi phối hợp nhiều nguồn.
- Retry áp dụng cho một nhánh hay toàn bộ pipeline.
- Lỗi có được chuyển thành dữ liệu hay vẫn là terminal signal.
- Cancellation có dừng nguồn và giải phóng tài nguyên không.
- Timeout và fallback có giữ đúng hợp đồng của API hay không.

### 7. Context và dữ liệu theo từng subscription

Reactor có **Context** gắn với subscription, thường được dùng để truyền metadata như tenant ID, correlation ID hoặc thông tin xác thực trong pipeline mà không phải truyền qua mọi hàm:

~~~java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

Mono<String> tenantId =
    Mono.deferContextual(context ->
        Mono.just(context.get("tenantId"))
    );

tenantId
    .contextWrite(Context.of("tenantId", "tenant-a"))
    .subscribe(System.out::println);
~~~

RxJava không cung cấp một cơ chế Context theo subscription tương đương trực tiếp trong lõi API. Ứng dụng RxJava thường truyền metadata rõ ràng trong đối tượng dữ liệu, dùng wrapper cho request hoặc tích hợp một thư viện context riêng. Không nên dựa vào **ThreadLocal** như thể nó tự truyền đúng qua mọi scheduler; khi pipeline đổi thread, vòng đời và phạm vi của ThreadLocal cần được quản lý riêng.

Nếu một module cần hoạt động với cả Reactor và RxJava, nên giữ metadata trong kiểu dữ liệu hoặc một abstraction ở ranh giới module. Adapter có thể chuyển đổi metadata phù hợp khi đi vào từng pipeline. Cách này giảm phụ thuộc vào cơ chế context riêng của một thư viện.

### 8. Kiểm thử pipeline

Reactor thường dùng **StepVerifier** để xác minh thứ tự phần tử, terminal signal, demand và thời gian ảo:

~~~java
import java.time.Duration;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1)).take(2)
    )
    .thenAwait(Duration.ofSeconds(2))
    .expectNext(0L, 1L)
    .verifyComplete();
~~~

RxJava cung cấp **TestObserver**, **TestSubscriber** và **TestScheduler**. TestSubscriber phù hợp với Flowable khi cần kiểm tra demand; TestObserver thường dùng với Observable, Single, Maybe hoặc Completable.

~~~java
import java.util.concurrent.TimeUnit;

import io.reactivex.rxjava3.core.Flowable;
import io.reactivex.rxjava3.schedulers.TestScheduler;
import io.reactivex.rxjava3.subscribers.TestSubscriber;

TestScheduler clock = new TestScheduler();
TestSubscriber<Long> subscriber =
    Flowable.interval(1, TimeUnit.SECONDS, clock)
        .take(2)
        .test();

clock.advanceTimeBy(2, TimeUnit.SECONDS);

subscriber
    .assertValues(0L, 1L)
    .assertComplete()
    .assertNoErrors();
~~~

Đồng hồ ảo của hai thư viện là hai cơ chế kiểm thử riêng. Khi chuyển pipeline từ Reactor sang RxJava, cần viết lại kiểm thử bằng công cụ tương ứng và xác minh hành vi, không chỉ chuyển cú pháp.

### 9. Interop qua Reactive Streams

Một lợi thế quan trọng là **Flux**/**Mono** và RxJava **Flowable** có thể trao đổi qua giao diện **org.reactivestreams.Publisher**. Điều này cho phép đặt ranh giới tích hợp mà không cần chuyển đổi từng phần tử thủ công.

Từ RxJava Flowable sang Reactor:

~~~java
import io.reactivex.rxjava3.core.Flowable;
import reactor.core.publisher.Flux;

Flowable<OrderEvent> rxEvents = rxEventClient.events();

Flux<OrderEvent> reactorEvents =
    Flux.from(rxEvents);
~~~

Từ Reactor sang RxJava Flowable:

~~~java
import io.reactivex.rxjava3.core.Flowable;
import reactor.core.publisher.Flux;

Flux<OrderEvent> reactorEvents = orderEventService.events();

Flowable<OrderEvent> rxEvents =
    Flowable.fromPublisher(reactorEvents);
~~~

Hai chiều chuyển đổi này giữ mô hình Reactive Streams và demand của Flowable. Chúng là lựa chọn phù hợp khi tích hợp một thư viện RxJava vào dịch vụ Reactor hoặc ngược lại. Hãy giữ adapter tại biên hệ thống để phần lõi không phải phụ thuộc cả hai thư viện.

Không phải mọi kiểu RxJava đều triển khai Publisher. **Observable**, **Single**, **Maybe** và **Completable** có các hợp đồng riêng. Muốn chuyển chúng sang Reactor, cần chọn cách biểu diễn tương ứng và quyết định rõ trường hợp rỗng hoặc lỗi. Ví dụ, chuyển Single thành Mono có thể dùng **single.toFlowable()** rồi **Mono.from(...)**; chuyển Maybe cần giữ khả năng hoàn tất rỗng. Không nên ép một Single thành kiểu có thể rỗng mà không xác định ý nghĩa nghiệp vụ, hoặc biến Observable thành Flowable mà không chọn chính sách backpressure.

### 10. Chọn thư viện theo kịch bản

| Kịch bản | Lựa chọn thường thuận lợi | Lý do |
| --- | --- | --- |
| Ứng dụng Spring WebFlux mới | Reactor | **Mono** và **Flux** là kiểu tích hợp tự nhiên của hệ sinh thái |
| Spring Data reactive hoặc R2DBC | Reactor | Giữ kiểu trả về xuyên suốt repository và service |
| Ứng dụng đã chuẩn hóa RxJava | RxJava | Giảm chuyển đổi, tận dụng code và kỹ năng hiện có |
| Thư viện ngoài trả về **Flowable** | RxJava hoặc adapter sang Reactor | Có thể giữ nguyên API hoặc chuyển tại ranh giới Publisher |
| Cần backpressure theo Reactive Streams | Reactor **Flux** hoặc RxJava **Flowable** | Cả hai tuân theo demand protocol |
| Sự kiện push không có demand và chấp nhận chính sách overflow riêng | RxJava **Observable** có thể phù hợp | Không có request protocol; phải tự thiết kế điều tiết |
| Một ứng dụng cần tích hợp cả hai hệ sinh thái | Chọn một thư viện làm mô hình chính | Giới hạn chuyển đổi ở các adapter được kiểm soát |

Đây là hướng lựa chọn thực tế, không phải quy tắc cứng. RxJava có thể dùng cho backend và Reactor có thể dùng ngoài Spring. Điều quan trọng là thư viện phải phù hợp với hợp đồng của nguồn dữ liệu, framework và yêu cầu vận hành.

### 11. Những câu hỏi cần trả lời trước khi quyết định

Trước khi đưa Reactor hoặc RxJava vào một module, hãy xác định:

1. Framework web, driver cơ sở dữ liệu và SDK đang trả về kiểu dữ liệu nào?
2. Một thao tác có thể hoàn tất rỗng, phải trả đúng một giá trị hay phát nhiều phần tử?
3. Consumer có cần demand/backpressure không? Nguồn có hỗ trợ hoặc có thể thích nghi với demand không?
4. Pipeline cần scheduler nào cho I/O blocking và công việc CPU-bound?
5. Ứng dụng có cần context theo subscription cho tenant, trace hoặc correlation ID không?
6. Công cụ kiểm thử nào đã được dùng và có hỗ trợ virtual time, demand, cancellation không?
7. Nếu phải interop, ranh giới chuyển đổi nằm ở đâu và có giữ đúng error/cancellation semantics không?
8. Đội ngũ có thể duy trì một mô hình reactive thống nhất hay phải hỗ trợ hai bộ API lâu dài?

### 12. Nguyên tắc tích hợp và chuyển đổi

Khi hai thư viện cùng tồn tại, hãy áp dụng một số nguyên tắc:

- Chọn một kiểu reactive làm hợp đồng chính trong mỗi module.
- Đặt adapter tại ranh giới với thư viện trả về kiểu khác.
- Chuyển đổi đúng cardinality: zero-or-one, exactly-one, completion-only hoặc many.
- Giữ backpressure khi chuyển giữa **Flux** và **Flowable**; không vô tình đi qua **Observable** nếu cần demand.
- Kiểm tra lại scheduler, error handling, retry và cancellation sau khi chuyển đổi.
- Không gọi **subscribe()** lồng bên trong service chỉ để nối hai pipeline; trả về Publisher để caller điều phối vòng đời.
- Viết kiểm thử ở hai phía adapter để xác nhận phần tử, lỗi, completion và cancellation.

Một module không nên để kiểu **Mono**, **Flux**, **Single**, **Maybe**, **Flowable** và **Observable** lan tràn qua mọi tầng nếu không có lý do rõ ràng. Việc giữ một abstraction nội bộ giúp thay đổi thư viện hoặc tích hợp thêm nguồn dữ liệu dễ kiểm soát hơn.

### 13. Kết luận lựa chọn

Nếu ứng dụng gắn chặt với Spring WebFlux và Spring Data reactive, Reactor thường giúp tích hợp tự nhiên và giữ kiểu dữ liệu xuyên suốt. Nếu hệ thống đã dùng RxJava hoặc thư viện chính trả về các kiểu RxJava, tiếp tục dùng RxJava có thể đơn giản và ít rủi ro hơn. Khi cần kết hợp hai hệ sinh thái, **Publisher** là ranh giới interop hữu ích cho **Flux**, **Mono** và **Flowable**; các kiểu khác cần được ánh xạ theo đúng cardinality và hợp đồng.

Lựa chọn tốt là lựa chọn giữ đúng ý nghĩa dữ liệu, demand, lỗi và vòng đời subscription trong môi trường thực tế. Hãy ưu tiên khả năng tích hợp, tính nhất quán của API và khả năng kiểm thử, rồi mới cân nhắc sự quen thuộc với tên toán tử. Cách tiếp cận này giúp module Java reactive phát triển ổn định dù sử dụng Reactor, RxJava hay kết hợp cả hai tại những ranh giới được xác định rõ.
