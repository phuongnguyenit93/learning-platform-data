# Dùng TestPublisher hoặc mock ở đúng ranh giới cần kiểm soát

Khi kiểm thử ứng dụng Spring Data Relational R2DBC, không phải mọi test đều cần kết nối database thật. Một unit test cho service thường chỉ cần kiểm soát repository trả về `Mono` hoặc `Flux` nào để xác nhận quy tắc nghiệp vụ. Một test cần kiểm soát thời điểm publisher phát dữ liệu, phát lỗi, hoàn tất rỗng, nhận request hoặc bị cancel có thể dùng `TestPublisher`. Ngược lại, khi cần xác nhận SQL, mapping, codec, transaction, generated ID hay hành vi của driver, phải kiểm thử với database thật hoặc môi trường tương đương.

Chọn đúng ranh giới giúp test tập trung vào điều cần chứng minh. Mock phù hợp để thay thế một dependency bên ngoài đơn vị đang kiểm thử. `TestPublisher` phù hợp để điều khiển tín hiệu Reactive Streams theo thời điểm do test quyết định. `StepVerifier` tiêu thụ publisher và kiểm tra tín hiệu đầu ra. Integration test kiểm tra sự phối hợp thực tế giữa Spring Data, driver và database.

Một nguyên tắc quan trọng: hãy mock repository khi kiểm thử logic service; đừng mock `Mono`, `Flux`, `Row`, `Connection` hoặc chuỗi nội bộ của `DatabaseClient` để giả lập toàn bộ database rồi kết luận rằng SQL thực tế đúng. Test ở tầng repository cần xác minh hành vi thật của persistence infrastructure.

## 1. Xác định ranh giới cần kiểm soát

Trước khi chọn công cụ, hãy xác định test đang muốn chứng minh điều gì.

| Mục tiêu kiểm thử | Ranh giới nên kiểm soát | Công cụ phù hợp |
| --- | --- | --- |
| Service chọn đúng nhánh khi repository có dữ liệu | Kết quả repository | Mockito mock trả `Mono.just(...)` |
| Service xử lý trường hợp không tìm thấy | Empty completion của repository | Mock trả `Mono.empty()` hoặc `TestPublisher` hoàn tất rỗng |
| Service chuyển lỗi thành lỗi nghiệp vụ | Error signal từ dependency | Mock trả `Mono.error(...)` |
| Publisher phát dữ liệu muộn hoặc lỗi sau một khoảng thời gian | Thời điểm phát tín hiệu upstream | `TestPublisher` và `StepVerifier` |
| Kiểm tra backpressure hoặc cancellation | Request/cancel của subscriber | `TestPublisher` và `StepVerifier` |
| Kiểm tra retry đăng ký lại publisher | Hành vi source theo từng subscription | `Mono.defer`, `TestPublisher` hoặc mock trả publisher có thể điều khiển |
| Kiểm tra repository tạo SQL đúng | Spring Data, dialect, driver và database | Integration test với database phù hợp |
| Kiểm tra generated ID, codec, mapping, transaction | Persistence stack thực tế | Integration test với đúng R2DBC driver/database |
| Kiểm tra API gọi dịch vụ ngoài | Client/service ở ranh giới service | Mock client hoặc HTTP stub server |

Không có một công cụ duy nhất phù hợp cho mọi tầng. Test càng gần database thì càng có khả năng phát hiện lỗi SQL, mapping và driver; đổi lại, test thường chậm hơn và cần môi trường database. Unit test bằng mock chạy nhanh, nhưng chỉ chứng minh logic bên trong ranh giới đã mock.

## 2. Dependency cần cho `TestPublisher` và `StepVerifier`

`TestPublisher` và `StepVerifier` nằm trong module `reactor-test`. Trong Gradle:

```kotlin
dependencies {
    testImplementation("io.projectreactor:reactor-test")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

Với Maven:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Nếu dự án dùng Spring Boot dependency management, để BOM quản lý version tương thích. `spring-boot-starter-test` thường cung cấp JUnit Jupiter, Mockito và các thư viện assertion phổ biến; kiểm tra dependency thực tế nếu dự án dùng cấu hình test tối giản.

Các import Reactor Test thường gặp:

```java
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;
```

Mockito thường dùng:

```java
import static org.mockito.Mockito.when;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
```

Không cần thêm `reactor-test` vào runtime dependency chỉ để ứng dụng chạy. Đây là thư viện phục vụ kiểm thử.

## 3. Mock repository bằng publisher thật

Giả sử service cần tìm customer và chuyển thành DTO:

```java
public record Customer(Long id, String name) {
}

public record CustomerView(Long id, String displayName) {
}

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {
}

@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<CustomerView> findView(Long id) {
        return repository.findById(id)
                .map(customer -> new CustomerView(
                        customer.id(), customer.name()
                ));
    }
}
```

Unit test có thể mock repository và trả một `Mono` thật:

```java
@ExtendWith(MockitoExtension.class)
class CustomerServiceTest {

    @Mock
    CustomerRepository repository;

    CustomerService service;

    @BeforeEach
    void setUp() {
        service = new CustomerService(repository);
    }

    @Test
    void mapsCustomerToView() {
        when(repository.findById(10L))
                .thenReturn(Mono.just(new Customer(10L, "Lan")));

        StepVerifier.create(service.findView(10L))
                .expectNext(new CustomerView(10L, "Lan"))
                .verifyComplete();

        verify(repository).findById(10L);
    }
}
```

Ở đây Mockito thay thế dependency repository. `Mono.just(...)` vẫn là publisher Reactor thật, còn `StepVerifier` subscribe vào kết quả của service để xác nhận `onNext` và `onComplete`.

Không nên mock chính `Mono<CustomerView>` bằng Mockito. `Mono` là abstraction reactive có nhiều semantics về subscription, demand, cancellation và terminal signal; dùng publisher thật sẽ làm test tự nhiên và ít phụ thuộc implementation hơn.

### Kiểm tra trường hợp không tìm thấy

Nếu service chuyển empty thành lỗi:

```java
public Mono<CustomerView> requireView(Long id) {
    return repository.findById(id)
            .map(customer -> new CustomerView(
                    customer.id(), customer.name()
            ))
            .switchIfEmpty(Mono.error(
                    new CustomerNotFoundException(id)
            ));
}
```

Test:

```java
@Test
void emitsNotFoundWhenRepositoryIsEmpty() {
    when(repository.findById(99L)).thenReturn(Mono.empty());

    StepVerifier.create(service.requireView(99L))
            .expectError(CustomerNotFoundException.class)
            .verify();

    verify(repository).findById(99L);
}
```

Mock trả `Mono.empty()` là đủ nếu test chỉ cần xác nhận quy tắc “không có customer thì phát lỗi”. Không cần `TestPublisher` chỉ để mô phỏng một empty publisher đơn giản.

### Kiểm tra lỗi dependency

```java
@Test
void propagatesRepositoryFailure() {
    when(repository.findById(10L))
            .thenReturn(Mono.error(new IllegalStateException("database unavailable")));

    StepVerifier.create(service.findView(10L))
            .expectError(IllegalStateException.class)
            .verify();
}
```

Test này xác nhận service không vô tình biến lỗi truy cập dữ liệu thành một giá trị thành công. Nếu service có `onErrorMap` hoặc `onErrorResume`, assertion cần kiểm tra đúng lỗi/giá trị theo hợp đồng của service.

## 4. Mockito mock kiểm soát lời gọi dependency, không kiểm soát thời điểm phát tín hiệu

Mock repository thường trả một publisher đã biết:

```java
when(repository.findById(10L))
        .thenReturn(Mono.just(customer));
```

Điều này phù hợp cho test mapping hoặc nhánh nghiệp vụ. Nhưng nếu cần phát dữ liệu sau khi test đã subscribe, phát lỗi ở một thời điểm cụ thể, xác nhận upstream có bị cancel hay không hoặc kiểm tra request được truyền tới publisher, mock tĩnh có thể không đủ thuận tiện.

Mockito có thể trả `Mono.defer`, `Flux.create` hoặc publisher tùy chỉnh, nhưng khi mục tiêu là điều khiển tín hiệu Reactive Streams, `TestPublisher` làm ý định test rõ hơn.

### Không nhầm thời điểm gọi method với thời điểm SQL chạy

Trong một service đơn giản:

```java
public Mono<Customer> find(Long id) {
    return repository.findById(id);
}
```

Lời gọi Java `repository.findById(id)` thường diễn ra khi method service xây dựng pipeline. Với repository reactive của Spring Data, publisher trả về thường cold và việc truy vấn database diễn ra khi publisher được subscribe.

Vì vậy, Mockito `verify(repository).findById(id)` chứng minh method repository đã được gọi để lấy publisher. Nó không chứng minh SQL đã được gửi tới database hoặc database trả kết quả. Những điều đó cần integration test.

Nếu service dùng `Mono.defer`:

```java
public Mono<Customer> findLazily(Long id) {
    return Mono.defer(() -> repository.findById(id));
}
```

thì method repository chỉ được gọi khi publisher được subscribe. Có thể kiểm tra:

```java
@Test
void callsRepositoryOnSubscription() {
    when(repository.findById(10L))
            .thenReturn(Mono.just(new Customer(10L, "Lan")));

    Mono<Customer> result = service.findLazily(10L);

    verifyNoInteractions(repository);

    StepVerifier.create(result)
            .expectNext(new Customer(10L, "Lan"))
            .verifyComplete();

    verify(repository).findById(10L);
}
```

Đặt assertion đúng thời điểm giúp tránh test sai về laziness. Đừng mặc định mọi repository method chỉ được gọi sau subscribe; điều đó phụ thuộc code service có bọc lời gọi trong `defer` hay không.

## 5. `TestPublisher` là gì?

`TestPublisher<T>` là publisher điều khiển được trong test. Test có thể chủ động phát phần tử, phát lỗi hoặc complete sau khi pipeline đã được subscribe. Nó đặc biệt hữu ích khi cần mô phỏng nguồn dữ liệu bất đồng bộ mà thời điểm phát tín hiệu do test quyết định.

Ví dụ:

```java
TestPublisher<Customer> source = TestPublisher.create();

Mono<Customer> result = source.mono();

StepVerifier.create(result)
        .then(() -> source.next(new Customer(10L, "Lan")))
        .expectNext(new Customer(10L, "Lan"))
        .verifyComplete();
```

`StepVerifier` bắt đầu subscription. Sau đó callback `then(...)` yêu cầu `TestPublisher` phát customer. Test xác nhận phần tử được chuyển qua pipeline và publisher hoàn tất.

Các thao tác điều khiển thường dùng:

| API | Ý nghĩa |
| --- | --- |
| `TestPublisher.create()` | Tạo publisher có thể điều khiển |
| `source.mono()` | Cung cấp view dạng `Mono` |
| `source.flux()` | Cung cấp view dạng `Flux` |
| `source.next(value)` | Phát một hoặc nhiều phần tử theo API varargs |
| `source.emit(values...)` | Phát các phần tử rồi complete |
| `source.complete()` | Complete mà không phát thêm phần tử |
| `source.error(error)` | Phát lỗi terminal |
| `source.assertWasSubscribed()` | Xác nhận có subscriber |
| `source.assertWasNotSubscribed()` | Xác nhận chưa có subscriber |
| `source.assertWasRequested()` | Xác nhận subscriber đã yêu cầu dữ liệu |
| `source.assertCancelled()` | Xác nhận publisher bị cancel |
| `source.assertMinRequested(n)` | Xác nhận tổng demand ít nhất đạt mức n |

Các assertion về request/cancel hữu ích khi kiểm tra hành vi của một publisher downstream. Tên API và chi tiết assertion cần khớp version `reactor-test` mà dự án đang sử dụng.

## 6. Dùng TestPublisher khi cần phát tín hiệu theo thời điểm

Giả sử service lấy customer rồi tạo DTO. Ta muốn chắc chắn service không phát kết quả trước khi upstream phát dữ liệu:

```java
@Test
void waitsUntilSourceEmitsCustomer() {
    TestPublisher<Customer> source = TestPublisher.create();
    when(repository.findById(10L)).thenReturn(source.mono());

    Mono<CustomerView> result = service.findView(10L);

    StepVerifier.create(result)
            .then(() -> source.assertWasSubscribed())
            .then(() -> source.next(new Customer(10L, "Lan")))
            .expectNext(new CustomerView(10L, "Lan"))
            .verifyComplete();
}
```

Ở đây `TestPublisher` được đưa qua mock repository. Mockito kiểm soát dependency nào được thay thế; `TestPublisher` kiểm soát tín hiệu của dependency đó. Hai công cụ có thể kết hợp thay vì phải chọn duy nhất một.

### Phát lỗi sau khi pipeline đã subscribe

```java
@Test
void forwardsLateUpstreamError() {
    TestPublisher<Customer> source = TestPublisher.create();
    when(repository.findById(10L)).thenReturn(source.mono());

    StepVerifier.create(service.findView(10L))
            .then(() -> source.assertWasSubscribed())
            .then(() -> source.error(new IllegalStateException("late failure")))
            .expectError(IllegalStateException.class)
            .verify();
}
```

Test này điều khiển thời điểm lỗi xảy ra sau subscription. Nó phù hợp khi kiểm tra pipeline xử lý lỗi đến muộn, ví dụ một nguồn event hoặc adapter reactive.

### Complete rỗng để kích hoạt fallback

```java
@Test
void usesFallbackWhenSourceCompletesEmpty() {
    TestPublisher<Customer> source = TestPublisher.create();
    when(repository.findById(10L)).thenReturn(source.mono());

    StepVerifier.create(service.requireView(10L))
            .then(() -> source.complete())
            .expectError(CustomerNotFoundException.class)
            .verify();
}
```

`complete()` không phát phần tử. Vì vậy `switchIfEmpty` trong service được kích hoạt. Nếu test chỉ cần kiểm tra nhánh empty tĩnh, `Mono.empty()` trong Mockito vẫn đơn giản hơn; `TestPublisher` có giá trị khi test cần điều khiển thời điểm complete hoặc phối hợp nhiều tín hiệu.

## 7. TestPublisher với `Flux` nhiều phần tử

Khi service xử lý một luồng nhiều customer, dùng `flux()`:

```java
public Flux<CustomerView> streamViews() {
    return repository.findAll()
            .map(customer -> new CustomerView(
                    customer.id(), customer.name()
            ));
}
```

Test:

```java
@Test
void mapsItemsAsTheyArrive() {
    TestPublisher<Customer> source = TestPublisher.create();
    when(repository.findAll()).thenReturn(source.flux());

    StepVerifier.create(service.streamViews())
            .then(() -> source.next(
                    new Customer(1L, "Lan"),
                    new Customer(2L, "Minh")
            ))
            .expectNext(
                    new CustomerView(1L, "Lan"),
                    new CustomerView(2L, "Minh")
            )
            .then(() -> source.complete())
            .verifyComplete();
}
```

TestPublisher cho phép phát một nhóm phần tử, sau đó phát thêm hoặc complete ở bước tiếp theo. Nhờ vậy test có thể xác nhận thứ tự và cách service xử lý stream theo từng đợt.

Nếu service dùng `collectList()`, nó chỉ phát list sau khi upstream complete. Test cần complete source trước khi mong đợi list:

```java
StepVerifier.create(service.loadAllViews())
        .then(() -> source.next(customerA, customerB))
        .then(() -> source.complete())
        .expectNext(List.of(viewA, viewB))
        .verifyComplete();
```

Không mong `collectList()` phát kết quả ngay sau `next(...)` nếu source chưa complete.

## 8. Test backpressure và demand

Reactive Streams sử dụng demand: subscriber yêu cầu số phần tử mà nó sẵn sàng nhận. `StepVerifier` có thể bắt đầu với demand bằng 0 rồi yêu cầu từng phần tử. `TestPublisher` có thể xác nhận upstream đã nhận request.

Ví dụ service trả stream trực tiếp sau mapping:

```java
public Flux<CustomerView> streamViews() {
    return repository.findAll()
            .map(customer -> new CustomerView(
                    customer.id(), customer.name()
            ));
}
```

Test demand:

```java
@Test
void requestsDataOnlyWhenDownstreamRequests() {
    TestPublisher<Customer> source = TestPublisher.create();
    when(repository.findAll()).thenReturn(source.flux());

    StepVerifier.create(service.streamViews(), 0)
            .then(() -> source.assertWasSubscribed())
            .then(() -> source.assertWasNotRequested())
            .thenRequest(1)
            .then(() -> source.assertMinRequested(1))
            .then(() -> source.next(new Customer(1L, "Lan")))
            .expectNext(new CustomerView(1L, "Lan"))
            .thenCancel()
            .verify();

    source.assertCancelled();
}
```

Test bắt đầu với initial request bằng 0. Sau `thenRequest(1)`, source có thể nhận demand. Test phát một customer, kiểm tra DTO và hủy subscription. `assertCancelled()` xác nhận cancellation được truyền ngược tới source.

### Không suy diễn demand một-một qua mọi operator

Một số operator có thể prefetch hoặc thay đổi cách yêu cầu dữ liệu. Ví dụ `buffer`, `flatMap`, `publishOn`, `limitRate` và `concatMap` có chiến lược request riêng. Do đó, không nên luôn khẳng định một request downstream tương ứng chính xác một request upstream. Dùng assertion về demand để kiểm tra hợp đồng cần thiết, và hiểu prefetch của operator đang dùng.

Nếu test một service có `flatMap` với concurrency/prefetch, hãy xác định chính xác hành vi mong đợi trước khi assert số request. TestPublisher có thể giúp quan sát request, nhưng không thay thế việc hiểu semantics của Reactor operator.

## 9. Test cancellation

Cancellation quan trọng khi client ngắt kết nối, timeout xảy ra hoặc operator downstream không cần dữ liệu nữa. Một service tốt nên truyền cancellation về upstream để ngừng công việc không còn cần thiết.

Ví dụ service:

```java
public Flux<CustomerView> streamViews() {
    return repository.findAll()
            .map(customer -> new CustomerView(
                    customer.id(), customer.name()
            ));
}
```

Test:

```java
@Test
void propagatesCancellationToSource() {
    TestPublisher<Customer> source = TestPublisher.create();
    when(repository.findAll()).thenReturn(source.flux());

    StepVerifier.create(service.streamViews(), 0)
            .thenRequest(1)
            .then(() -> source.next(new Customer(1L, "Lan")))
            .expectNext(new CustomerView(1L, "Lan"))
            .thenCancel()
            .verify();

    source.assertCancelled();
}
```

Sau khi nhận một phần tử, verifier hủy subscription. TestPublisher xác nhận source nhận cancellation. Nếu service thêm operator có buffering hoặc tạo publisher con, cần kiểm tra cancellation ở ranh giới có ý nghĩa và không giả định mọi tài nguyên bên trong được hủy theo cùng thời điểm.

### Cancellation khác error

Cancellation không phải `onError`. Không dùng `expectError` để kiểm tra cancellation. `StepVerifier.thenCancel()` xác nhận subscriber hủy, còn `TestPublisher.assertCancelled()` xác nhận upstream quan sát cancellation.

## 10. Test nhánh `switchIfEmpty` với TestPublisher

Khi test nhánh fallback, có thể kiểm tra cả source và publisher thay thế. Ví dụ service:

```java
public Mono<Customer> findOrDefault(Long id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.defer(() ->
                    repository.findDefaultCustomer()
            ));
}
```

Test trường hợp có dữ liệu:

```java
@Test
void doesNotSubscribeFallbackWhenPrimaryHasValue() {
    TestPublisher<Customer> primary = TestPublisher.create();
    TestPublisher<Customer> fallback = TestPublisher.create();

    when(repository.findById(1L)).thenReturn(primary.mono());
    when(repository.findDefaultCustomer()).thenReturn(fallback.mono());

    StepVerifier.create(service.findOrDefault(1L))
            .then(() -> primary.next(new Customer(1L, "Lan")))
            .expectNext(new Customer(1L, "Lan"))
            .verifyComplete();

    fallback.assertWasNotSubscribed();
    verify(repository, never()).findDefaultCustomer();
}
```

Test trường hợp source empty:

```java
@Test
void subscribesFallbackWhenPrimaryIsEmpty() {
    TestPublisher<Customer> primary = TestPublisher.create();
    TestPublisher<Customer> fallback = TestPublisher.create();

    when(repository.findById(1L)).thenReturn(primary.mono());
    when(repository.findDefaultCustomer()).thenReturn(fallback.mono());

    StepVerifier.create(service.findOrDefault(1L))
            .then(() -> primary.complete())
            .then(() -> fallback.assertWasSubscribed())
            .then(() -> fallback.next(new Customer(0L, "Default")))
            .expectNext(new Customer(0L, "Default"))
            .verifyComplete();

    verify(repository).findDefaultCustomer();
}
```

Để dùng `never()` cần static import tương ứng từ Mockito. Điểm test cần chứng minh là fallback chỉ được subscribe khi primary complete rỗng. Nếu chỉ cần kiểm tra kết quả cuối, mock trả `Mono.just`/`Mono.empty` sẽ gọn hơn; TestPublisher được chọn vì test còn kiểm tra thời điểm subscription và nhánh thực sự được kích hoạt.

## 11. Test retry và số lần subscribe

Retry đăng ký lại upstream publisher. Khi muốn xác nhận số lần source được subscribe, có thể dùng `TestPublisher` hoặc publisher được tạo bằng `Mono.defer`.

Ví dụ một source phát lỗi hai lần rồi thành công:

```java
AtomicInteger attempts = new AtomicInteger();

Mono<String> source = Mono.defer(() -> {
    int attempt = attempts.incrementAndGet();
    if (attempt < 3) {
        return Mono.error(new IllegalStateException("temporary"));
    }
    return Mono.just("ok");
});

StepVerifier.create(source.retry(2))
        .expectNext("ok")
        .verifyComplete();

assertThat(attempts).hasValue(3);
```

`Mono.defer` chạy supplier cho mỗi subscription, vì vậy counter đếm số lần thực thi upstream. Với Mockito, lưu ý rằng method repository có thể chỉ được gọi một lần để lấy publisher, còn publisher đó được subscribe lại nhiều lần. Mockito `verify(repository, times(3)).findById(id)` không nhất thiết phản ánh ba lần SQL nếu publisher được tạo một lần rồi retry ở bên ngoài.

Nếu cần test số lần method tạo publisher được gọi, đặt lời gọi repository bên trong `Mono.defer` và dùng Mockito `thenAnswer` hoặc `verify` phù hợp. Nếu cần test số lần publisher được subscribe, đếm trong supplier của `Mono.defer` hoặc dùng TestPublisher assertion phù hợp.

### Ví dụ mock repository tạo publisher theo từng lần gọi

```java
AtomicInteger attempts = new AtomicInteger();

when(repository.findById(10L)).thenAnswer(invocation ->
        Mono.defer(() -> {
            int attempt = attempts.incrementAndGet();
            if (attempt < 3) {
                return Mono.error(new IllegalStateException("temporary"));
            }
            return Mono.just(new Customer(10L, "Lan"));
        })
);

StepVerifier.create(service.findWithRetry(10L))
        .expectNext(new Customer(10L, "Lan"))
        .verifyComplete();

assertThat(attempts).hasValue(3);
```

Trong ví dụ này supplier của `Mono.defer` được gọi mỗi lần source được subscribe, do đó counter phản ánh số lần thực thi mô phỏng. Mockito `thenAnswer` chỉ chạy khi service gọi method mock; nếu service gọi method một lần rồi giữ publisher, `thenAnswer` cũng chỉ được gọi một lần. Cần hiểu chính xác counter đang đếm method invocation hay publisher subscription.

## 12. Mock ở đúng ranh giới service

Một unit test service nên thay thế dependency bên ngoài service, chẳng hạn:

- Repository mà service gọi.
- Client HTTP/gRPC.
- Message publisher hoặc gateway.
- Clock, ID generator hoặc policy provider khi cần kiểm soát thời gian/giá trị.

Không cần mock các object nội bộ mà service tự tạo, ví dụ DTO, `Mono.just`, `Flux.map` hoặc một mapper thuần nếu test có thể gọi trực tiếp.

Ví dụ service phối hợp repository và một client ngoài:

```java
public Mono<OrderView> loadOrder(Long id) {
    return orderRepository.findById(id)
            .switchIfEmpty(Mono.error(new OrderNotFoundException(id)))
            .flatMap(order -> customerClient.findName(order.customerId())
                    .map(name -> new OrderView(order.id(), name)));
}
```

Unit test có thể mock cả hai dependency, nhưng publisher trả về vẫn là publisher thật:

```java
when(orderRepository.findById(100L))
        .thenReturn(Mono.just(order));
when(customerClient.findName(20L))
        .thenReturn(Mono.just("Lan"));

StepVerifier.create(service.loadOrder(100L))
        .expectNext(new OrderView(100L, "Lan"))
        .verifyComplete();

verify(orderRepository).findById(100L);
verify(customerClient).findName(20L);
```

Test này chứng minh service truyền đúng customer ID và ghép đúng response. Nó không chứng minh query order hoặc HTTP request thực tế đúng; những phần đó cần test ở ranh giới repository/client tương ứng.

## 13. Vì sao không nên mock sâu `DatabaseClient`?

`DatabaseClient` có fluent API nhiều tầng:

```java
databaseClient.sql(sql)
        .bind("id", id)
        .map((row, metadata) -> ...)
        .one();
```

Mock từng interface lồng nhau có thể khiến test phụ thuộc vào cách triển khai nội bộ của Spring. Một thay đổi nhỏ trong chuỗi fluent API có thể làm test hỏng dù hành vi SQL không đổi. Mock sâu cũng không xác nhận:

- SQL có hợp lệ trên database không.
- Bind marker được chuyển đổi đúng không.
- Kiểu dữ liệu có codec không.
- Alias cột và mapping `Row` có đúng không.
- Transaction có rollback thật không.
- Generated values có được driver trả về không.

Nếu logic service gọi một adapter riêng, hãy mock adapter đó. Nếu test chính adapter dùng `DatabaseClient`, nên chạy integration test với database phù hợp. Có thể kiểm thử hàm mapping thuần bằng dữ liệu fixture nếu mapping đã được tách thành một function dễ gọi, nhưng vẫn cần ít nhất một integration test xác nhận `Row`/driver thực tế cung cấp dữ liệu như mong đợi.

## 14. Ranh giới giữa unit test và integration test R2DBC

Một cách phân chia thực tế:

| Tầng | Thành phần thật | Thành phần có thể thay thế | Điều test chứng minh |
| --- | --- | --- | --- |
| Unit test service | Service, Reactor operators, DTO mapping | Repository/client/clock | Quy tắc nghiệp vụ và cách phối hợp publisher |
| Test reactive flow | Pipeline service/adapter | Nguồn publisher bằng TestPublisher | Timing, signal, demand, cancellation, fallback |
| Repository integration | Spring Data repository, mapping, driver, database | Dịch vụ ngoài nếu không liên quan | SQL, mapping, codec, constraints, generated ID |
| Transaction integration | Transaction manager, connection factory, database | External API nếu không nằm trong transaction | Commit/rollback và resource binding |
| End-to-end | Application wiring và các thành phần chính | Hệ thống ngoài có thể dùng stub | Hành vi toàn luồng gần production |

Không cần chạy database thật cho mọi unit test. Ngược lại, không thể chứng minh persistence đúng chỉ bằng mock repository.

## 15. Integration test repository với database thật

Để kiểm tra Spring Data R2DBC, nên dùng database cùng loại với production, thường qua Testcontainers hoặc môi trường test được quản lý riêng.

Ví dụ khung test với Spring Boot:

```java
@SpringBootTest
class CustomerRepositoryIntegrationTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void savesAndReadsCustomer() {
        StepVerifier.create(
                repository.save(new Customer(null, "Lan"))
        )
        .assertNext(saved -> {
            assertThat(saved.id()).isNotNull();
            assertThat(saved.name()).isEqualTo("Lan");
        })
        .verifyComplete();
    }
}
```

Ví dụ giả định entity và constructor phù hợp với mapping dự án, database đã được khởi động và migration đã chạy. Cấu hình Testcontainers/R2DBC URL phụ thuộc server và Spring Boot version. Với test repository, cần xác nhận container được cấu hình trước khi application context tạo `ConnectionFactory`.

Các điều cần kiểm tra bằng integration test:

- `@Table`, `@Column`, `@Id` và naming strategy.
- Insert/update/delete thực tế.
- Generated ID và giá trị default.
- Mapping `NULL`, `UUID`, `Instant`, `BigDecimal`, JSON hoặc kiểu riêng.
- `@Version` và optimistic locking.
- `@MappedCollection` hoặc quan hệ aggregate nếu sử dụng.
- Custom conversions và entity callbacks.
- SQL `@Query`, join, pagination và upsert theo dialect.

H2 không thay thế hoàn toàn PostgreSQL, MySQL, MariaDB hoặc SQL Server khi ứng dụng phụ thuộc cú pháp, kiểu dữ liệu, generated values hay transaction semantics riêng.

## 16. Integration test transaction và lỗi giữa chừng

Nếu service ghi nhiều bảng trong một reactive transaction, test cần chứng minh rollback thật:

```java
@Transactional
public Mono<Void> createOrderThenFail(Order order) {
    return orderRepository.save(order)
            .flatMap(saved -> auditRepository.save(
                    new AuditEntry(saved.id(), "CREATED")
            ))
            .then(Mono.error(new IllegalStateException("force rollback")));
}
```

Integration test có thể gọi service, xác nhận publisher phát lỗi, rồi truy vấn lại cả hai bảng bằng một thao tác ngoài transaction test để kiểm tra không còn dữ liệu được ghi. Cần cẩn thận nếu test method tự được đánh dấu `@Transactional`: transaction của test có thể che kết quả commit/rollback hoặc làm truy vấn xác minh chạy trong cùng transaction. Hãy thiết kế transaction boundary của test rõ ràng.

Mock repository có thể xác nhận service nối đúng các publisher, nhưng không chứng minh `R2dbcTransactionManager` dùng cùng connection, database thực sự rollback hoặc driver xử lý cancellation đúng.

## 17. TestPublisher và hot/cold source

Reactor TestPublisher có thể được tạo với các chế độ cold hoặc hot:

- **Cold TestPublisher** có thể giữ các tín hiệu được phát trước khi subscriber đến và phát chúng cho subscriber theo semantics cold.
- **Hot TestPublisher** phát tín hiệu cho subscriber hiện tại; tín hiệu phát khi chưa có subscriber không được phát lại cho subscriber đến sau.

Khi test thời điểm subscribe và phát dữ liệu, chọn chế độ phù hợp với source mà ứng dụng đang tích hợp. Với event source hoặc callback API, hot behavior có thể quan trọng; với một publisher tính toán lại theo subscription, cold behavior thường gần semantics hơn.

Ví dụ ý tưởng với hot source:

```java
TestPublisher<String> hot = TestPublisher.createHot();
hot.next("before-subscribe");

StepVerifier.create(hot.flux())
        .then(() -> hot.next("after-subscribe"))
        .expectNext("after-subscribe")
        .then(() -> hot.complete())
        .verifyComplete();
```

Tín hiệu phát trước subscription không được mong đợi phát lại cho subscriber hot đến sau. Khi cần giữ tín hiệu trước subscriber, dùng cold publisher hoặc buffer semantics phù hợp.

Với cold source:

```java
TestPublisher<String> cold = TestPublisher.createCold();
cold.next("queued");

StepVerifier.create(cold.flux())
        .expectNext("queued")
        .then(() -> cold.complete())
        .verifyComplete();
```

Các chế độ và API cụ thể cần theo đúng Reactor Test version. Tránh dùng hot/cold chỉ vì tên gọi; hãy mô phỏng semantics thực tế của nguồn publisher mà adapter đang nhận.

## 18. TestPublisher không thay thế `StepVerifier`

Hai công cụ có vai trò bổ sung:

- `TestPublisher` điều khiển source: phát `next`, `error`, `complete`, quan sát request/cancel.
- `StepVerifier` là subscriber kiểm thử: đăng ký vào publisher, yêu cầu dữ liệu và xác nhận chuỗi tín hiệu.

Ví dụ:

```java
TestPublisher<Integer> source = TestPublisher.create();
Flux<Integer> result = source.flux().map(value -> value * 2);

StepVerifier.create(result)
        .then(() -> source.next(2))
        .expectNext(4)
        .then(() -> source.complete())
        .verifyComplete();
```

Chỉ tạo `TestPublisher` mà không subscribe kết quả thì không kiểm tra được pipeline. Chỉ dùng `StepVerifier` với `Flux.just(...)` phù hợp cho test output thông thường, nhưng không cho phép điều khiển tín hiệu upstream theo thời điểm như TestPublisher.

## 19. Dùng `createNoncompliant` khi kiểm tra nguồn vi phạm Reactive Streams

`TestPublisher.createNoncompliant(...)` cho phép tạo publisher cố ý vi phạm một số quy tắc Reactive Streams, ví dụ phát tín hiệu trái với demand hoặc phát sau terminal signal, tùy `Violation` được chọn.

Đây là công cụ chuyên biệt để kiểm tra adapter hoặc operator tự viết có chịu được nguồn publisher không tuân thủ hợp đồng hay không. Không dùng nó trong test thông thường cho repository R2DBC. Một nguồn không compliant có thể tạo hành vi không đại diện cho publisher hợp lệ và khiến test khó diễn giải.

Chỉ dùng khi:

- Đang xây dựng một adapter phải tiếp nhận publisher từ thư viện bên ngoài không đáng tin cậy.
- Cần xác nhận component xử lý/loại bỏ tín hiệu vi phạm theo yêu cầu.
- Test nêu rõ violation nào đang được mô phỏng và lý do.

Với luồng repository và driver R2DBC chuẩn, dùng `TestPublisher.create()` hoặc `createCold()`/`createHot()` là đủ.

## 20. Kiểm tra publisher được gọi hay không: mock hay TestPublisher?

Đôi khi test cần xác nhận nhánh fallback không được gọi. Mockito `verify` kiểm tra lời gọi method dependency; TestPublisher assertion kiểm tra publisher có subscriber hay không. Hai điều này không hoàn toàn giống nhau.

Ví dụ service:

```java
public Mono<Customer> findOrDefault(Long id) {
    return repository.findById(id)
            .switchIfEmpty(Mono.defer(repository::findDefaultCustomer));
}
```

Nếu muốn kiểm tra service không gọi method fallback, dùng:

```java
verify(repository, never()).findDefaultCustomer();
```

Nếu fallback publisher đã được tạo trước và muốn kiểm tra nó không được subscribe, dùng TestPublisher:

```java
fallback.assertWasNotSubscribed();
```

Với `Mono.defer`, lời gọi method tạo fallback publisher cũng bị trì hoãn. Vì vậy, `verify(..., never())` kiểm tra method chưa được gọi, còn `assertWasNotSubscribed()` kiểm tra source chưa được subscribe. Chọn assertion theo đúng hành vi cần bảo đảm.

## 21. Không dùng TestPublisher để giả lập driver hoặc connection

`TestPublisher` có thể thay thế một `Publisher` ở ranh giới của unit test, nhưng nó không mô phỏng giao thức R2DBC. Nó không xác nhận:

- Driver mở và đóng connection đúng.
- SQL được gửi và database parse đúng.
- Bind parameter được encode đúng kiểu.
- `Row` chứa metadata và codec đúng.
- Connection pool trả connection sau cancel.
- Transaction commit/rollback trên server.
- Generated values được server/driver trả về.

Nếu cần kiểm tra những hành vi này, dùng database thật hoặc Testcontainers với driver thực tế. Không thể chứng minh generated ID hoạt động bằng cách cho TestPublisher phát một `Customer` đã gán ID sẵn.

## 22. Mock repository trong service test: những lỗi thường gặp

### Mock trả `null` thay vì publisher

Một reactive repository method cần trả publisher:

```java
when(repository.findById(id)).thenReturn(Mono.empty());
```

Không để mock trả `null`. Gọi `.map`, `.switchIfEmpty` trên null sẽ gây `NullPointerException`, đây là lỗi cấu hình test chứ không phải semantics “không tìm thấy”.

### Dùng `Mono.just(null)`

Reactor không cho phép `Mono.just(null)`. Dùng `Mono.empty()` để biểu diễn không có phần tử:

```java
when(repository.findById(id)).thenReturn(Mono.empty());
```

Nếu cần chuyển một nullable Java value thành publisher, dùng `Mono.justOrEmpty(value)`.

### Gọi `block()` để assertion

Không cần block publisher trong unit test reactive. Dùng `StepVerifier` để kiểm tra tín hiệu:

```java
StepVerifier.create(service.findView(id))
        .expectNext(expected)
        .verifyComplete();
```

`block()` tạo subscription và chặn thread; dùng nó có thể che khuất cancellation/backpressure và làm test không giống cách ứng dụng reactive được tiêu thụ.

### Chỉ verify method call mà không subscribe publisher

```java
Mono<CustomerView> result = service.findView(id);
verify(repository).findById(id);
```

Đoạn này có thể chứng minh method repository đã được gọi khi assembly, nhưng chưa chứng minh publisher được tiêu thụ hoặc output đúng. Hãy dùng `StepVerifier` để subscribe và xác nhận kết quả.

### Dùng một publisher mutable cho nhiều test

`TestPublisher` có trạng thái subscription và terminal signal. Tạo publisher mới cho từng test để tránh tín hiệu/cancel từ test trước ảnh hưởng test sau. Không chia sẻ một TestPublisher static giữa nhiều test chạy song song.

## 23. Test retry với Mockito và TestPublisher

Giả sử service retry một lần khi dependency lỗi transient:

```java
public Mono<Customer> findWithRetry(Long id) {
    return Mono.defer(() -> repository.findById(id))
            .retryWhen(Retry.max(1));
}
```

Có thể dùng Mockito `thenAnswer` để trả publisher khác theo mỗi lần gọi:

```java
AtomicInteger calls = new AtomicInteger();

when(repository.findById(10L)).thenAnswer(invocation -> {
    if (calls.incrementAndGet() == 1) {
        return Mono.error(new R2dbcTransientResourceException("temporary"));
    }
    return Mono.just(new Customer(10L, "Lan"));
});

StepVerifier.create(service.findWithRetry(10L))
        .expectNext(new Customer(10L, "Lan"))
        .verifyComplete();

assertThat(calls).hasValue(2);
```

Ở đây `Mono.defer` bao quanh lời gọi repository nên method mock được gọi lại khi retry resubscribe. Nếu bỏ `defer`, method có thể chỉ được gọi một lần khi service tạo pipeline, còn publisher trả về được subscribe lại.

Nếu test muốn điều khiển lỗi đến muộn rồi quyết định publisher có thành công ở lần sau hay không, có thể dùng TestPublisher riêng cho từng attempt hoặc một factory publisher có trạng thái được kiểm soát. Tuy nhiên, không nên làm test phức tạp hơn nhu cầu: với retry logic đơn giản, `Mono.defer` và `AtomicInteger` thường rõ ràng hơn.

## 24. Test concurrency và race condition ở ranh giới phù hợp

Một số lỗi chỉ xuất hiện khi nhiều subscription chạy đồng thời, ví dụ hai request cùng tạo customer với một email duy nhất. TestPublisher có thể giúp điều khiển thời điểm source phát dữ liệu để dựng tình huống race trong unit test, nhưng nó không chứng minh database constraint bảo vệ đúng.

Ví dụ logic service `findOrCreate` có thể được kiểm tra với hai publisher cùng complete empty, nhưng kết quả test chỉ chứng minh service chọn nhánh insert ở cả hai subscription. Để chứng minh chỉ một hàng được tạo, phải chạy hai transaction thực sự trên database có unique constraint và xác nhận một insert thành công, request còn lại xử lý duplicate đúng.

Khi test concurrency với database:

- Dùng đúng database engine và isolation level.
- Khởi tạo dữ liệu sạch và đồng bộ điểm bắt đầu của hai thao tác.
- Không dựa vào sleep để tạo race nếu có thể dùng latch/barrier hoặc test hook xác định.
- Kiểm tra trạng thái database cuối cùng và exception được dịch.
- Bảo đảm test dọn dữ liệu và không chia sẻ unique key với test song song khác.

## 25. Một chiến lược test theo tầng

Một module R2DBC thường cần kết hợp nhiều loại test:

### Unit test service

- Mock repository/client.
- Trả `Mono.just`, `Mono.empty`, `Flux.just`, `Mono.error`.
- Dùng `StepVerifier` kiểm tra output và terminal signal.
- Verify dependency được gọi với đúng tham số.
- Không khởi động database.

### Reactive flow test

- Dùng `TestPublisher` để phát dữ liệu muộn.
- Kiểm tra empty/error/complete.
- Kiểm tra demand và cancellation.
- Kiểm tra retry hoặc fallback khi timing là một phần của behavior.
- Dùng virtual time khi cần kiểm tra delay/timeout mà không chờ thật.

### Repository integration test

- Khởi động database cùng loại production.
- Dùng R2DBC driver thực tế và migration thật.
- Kiểm tra SQL, mapping, codecs, generated keys, constraints.
- Không mock repository đang được kiểm tra.

### Transaction integration test

- Dùng `R2dbcTransactionManager` thật.
- Kiểm tra commit và rollback.
- Kiểm tra cùng `ConnectionFactory` và connection binding.
- Kiểm tra cancellation/timeout nếu đó là behavior cần bảo đảm.

Không cần lặp lại toàn bộ mọi trường hợp ở mọi tầng. Unit test nên tập trung vào logic nhanh; integration test nên tập trung vào contract với database và driver.

## 26. Ví dụ đầy đủ: service dùng mock và TestPublisher

Service:

```java
public interface CustomerRepository {
    Mono<Customer> findById(Long id);
    Flux<Customer> findAll();
}

public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Mono<CustomerView> findView(Long id) {
        return repository.findById(id)
                .map(customer -> new CustomerView(
                        customer.id(), customer.name()
                ))
                .switchIfEmpty(Mono.error(
                        new CustomerNotFoundException(id)
                ));
    }

    public Flux<CustomerView> streamViews() {
        return repository.findAll()
                .map(customer -> new CustomerView(
                        customer.id(), customer.name()
                ));
    }
}
```

Test class:

```java
@ExtendWith(MockitoExtension.class)
class CustomerServiceTest {

    @Mock
    CustomerRepository repository;

    CustomerService service;

    @BeforeEach
    void setUp() {
        service = new CustomerService(repository);
    }

    @Test
    void mapsFoundCustomer() {
        when(repository.findById(1L))
                .thenReturn(Mono.just(new Customer(1L, "Lan")));

        StepVerifier.create(service.findView(1L))
                .expectNext(new CustomerView(1L, "Lan"))
                .verifyComplete();

        verify(repository).findById(1L);
    }

    @Test
    void errorsWhenCustomerIsMissing() {
        when(repository.findById(1L)).thenReturn(Mono.empty());

        StepVerifier.create(service.findView(1L))
                .expectError(CustomerNotFoundException.class)
                .verify();
    }

    @Test
    void mapsItemsFromControllableSource() {
        TestPublisher<Customer> source = TestPublisher.create();
        when(repository.findAll()).thenReturn(source.flux());

        StepVerifier.create(service.streamViews())
                .then(() -> source.next(new Customer(1L, "Lan")))
                .expectNext(new CustomerView(1L, "Lan"))
                .then(() -> source.next(new Customer(2L, "Minh")))
                .expectNext(new CustomerView(2L, "Minh"))
                .then(() -> source.complete())
                .verifyComplete();
    }

    @Test
    void propagatesCancellation() {
        TestPublisher<Customer> source = TestPublisher.create();
        when(repository.findAll()).thenReturn(source.flux());

        StepVerifier.create(service.streamViews(), 0)
                .thenRequest(1)
                .then(() -> source.next(new Customer(1L, "Lan")))
                .expectNext(new CustomerView(1L, "Lan"))
                .thenCancel()
                .verify();

        source.assertCancelled();
    }
}
```

Ví dụ gom bốn mục tiêu vào cùng một class để minh họa; trong dự án có thể tách test theo behavior. Các record `Customer`, `CustomerView` và exception cần được khai báo theo code thực tế. `TestPublisher` được tạo mới trong từng test để không chia sẻ state.

## 27. Lỗi thường gặp khi chọn sai ranh giới

| Biểu hiện | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Unit test cần database chỉ để test nhánh service | Service test đang kiểm soát quá sâu persistence | Mock repository và trả publisher thật |
| Test không điều khiển được thời điểm source phát dữ liệu | Mock trả `Mono.just`/`Flux.just` cố định | Dùng `TestPublisher` |
| Test mock pass nhưng SQL production lỗi | Repository bị mock trong test đang muốn kiểm tra SQL | Viết integration test với database/driver thật |
| Mock trả `null` gây NPE | Chưa stub reactive method | Trả `Mono.empty()`, `Flux.empty()` hoặc publisher phù hợp |
| Dùng `Mono.just(null)` | Reactor không cho phép null element | Dùng `Mono.empty()` hoặc `Mono.justOrEmpty()` |
| `verify` thành công nhưng không có output assertion | Chỉ kiểm tra lời gọi method, chưa consume publisher | Dùng `StepVerifier` |
| Retry count sai | Nhầm method invocation với publisher subscription | Đếm đúng ranh giới; dùng `defer` để tạo lại source |
| TestPublisher không nhận tín hiệu mong đợi | Source chưa subscribe, đã terminal hoặc sai hot/cold semantics | Assertion subscription và điều khiển đúng thứ tự |
| Test backpressure mong request chính xác nhưng thất bại | Operator prefetch hoặc thay đổi demand | Xem semantics operator, assert mức demand phù hợp |
| Cancellation không được quan sát | Downstream chưa cancel hoặc source không phải upstream đang kiểm tra | Dùng `thenCancel()` và assert đúng publisher |
| Test chạy không ổn định khi song song | Chia sẻ TestPublisher hoặc mutable mock state | Tạo fixture riêng cho mỗi test |
| Mock sâu `DatabaseClient` rất mong manh | Test phụ thuộc fluent chain implementation | Tách adapter và dùng integration test cho SQL |
| H2 pass nhưng SQL Server/MySQL/PostgreSQL lỗi | Khác dialect, kiểu dữ liệu và driver | Chạy test với database production-compatible |

## 28. Quy trình chọn mock hay TestPublisher

Trước khi viết test, hãy trả lời:

1. Đối tượng đang kiểm thử là service, reactive adapter hay repository?
2. Dependency nào nằm ngoài ranh giới của đối tượng đó?
3. Test chỉ cần kết quả cố định hay cần điều khiển thời điểm phát tín hiệu?
4. Có cần quan sát request, backpressure hoặc cancellation không?
5. Có cần xác nhận SQL, mapping, driver, transaction hoặc constraint không?

Từ đó chọn:

- **Mock trả publisher thật** nếu chỉ cần điều khiển kết quả dependency.
- **Mock kết hợp TestPublisher** nếu cần thay dependency và kiểm soát tín hiệu theo thời điểm.
- **TestPublisher trực tiếp** nếu test một adapter/pipeline nhận `Publisher` và không cần mock object khác.
- **Database integration test** nếu behavior phụ thuộc SQL Server/database, driver, mapping hoặc transaction.

Không chọn TestPublisher chỉ vì code dùng Reactor. Một `Mono.just`, `Mono.empty` hoặc `Mono.error` thường là fixture đơn giản và rõ nhất. Dùng TestPublisher khi quyền điều khiển tín hiệu mang lại giá trị cho test.

## 29. Ghi nhớ

- Mock repository ở unit test service để kiểm soát dependency; trả `Mono`/`Flux` thật thay vì mock reactive type.
- `StepVerifier` subscribe publisher và xác nhận `onNext`, `onComplete`, `onError`, request và cancellation.
- `TestPublisher` cho phép test chủ động phát dữ liệu, empty completion, error và quan sát subscription/request/cancel.
- Dùng mock tĩnh cho kết quả đơn giản; dùng TestPublisher khi cần điều khiển thời điểm hoặc tín hiệu upstream.
- Mockito verify method invocation không đồng nghĩa SQL đã chạy; publisher reactive thường chỉ thực thi khi được subscribe.
- Với `Mono.defer`, dependency method có thể chỉ được gọi khi subscription bắt đầu; đặt verify đúng thời điểm.
- Retry resubscribe publisher; số lần gọi repository method và số lần subscribe publisher có thể khác nhau.
- Không mock sâu `DatabaseClient`, `Row` hoặc `Connection` để chứng minh SQL/driver đúng.
- Repository integration test cần database và R2DBC driver tương ứng để kiểm tra mapping, codec, generated values, constraint và transaction.
- TestPublisher không mô phỏng database protocol hoặc connection pool; nó chỉ điều khiển publisher ở ranh giới test.
- Kiểm tra cancellation bằng `StepVerifier.thenCancel()` và assertion trên source; cancellation khác error.
- Kiểm tra backpressure có tính đến prefetch và semantics của Reactor operators.
- Tạo TestPublisher mới cho từng test; không chia sẻ publisher mutable giữa các test chạy song song.
- Chỉ dùng non-compliant TestPublisher khi mục tiêu là kiểm tra nguồn vi phạm Reactive Streams.

Chọn mock hay TestPublisher dựa trên hành vi cần kiểm soát. Mock giúp cô lập service khỏi repository/client; TestPublisher giúp chủ động điều khiển tín hiệu và demand của nguồn reactive; StepVerifier xác nhận publisher đầu ra. Khi cần chứng minh SQL, mapping, codec, generated key hoặc transaction R2DBC hoạt động thật, hãy chuyển sang integration test với database và driver phù hợp.
