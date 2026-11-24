# Kiểm thử

## Phân lớp kiểm thử toán tử, thành phần và tích hợp

Một pipeline reactive có thể đúng ở từng toán tử nhưng vẫn sai khi kết hợp với service, database hoặc HTTP server. Ví dụ, phép `flatMap` có thể biến đổi dữ liệu chính xác, nhưng service lại gọi sai repository; repository có thể trả về Publisher đúng kiểu nhưng transaction không được giữ trong suốt chuỗi thao tác; endpoint có thể trả dữ liệu đúng nhưng không kết thúc khi client hủy kết nối.

Để kiểm soát những rủi ro này, hãy phân lớp kiểm thử theo ranh giới cần xác minh:

- **Kiểm thử toán tử:** xác minh một pipeline nhỏ có phát đúng phần tử, lỗi, completion, demand và cancellation hay không.
- **Kiểm thử thành phần:** xác minh một service hoặc adapter phối hợp đúng các Publisher và dependency của nó.
- **Kiểm thử tích hợp:** xác minh nhiều thành phần thật hoạt động cùng nhau qua ranh giới như HTTP, R2DBC, transaction hoặc broker.

Trong Project Reactor, `StepVerifier`, `TestPublisher` và `PublisherProbe` hỗ trợ kiểm tra hợp đồng tín hiệu. JUnit, Mockito, WebTestClient và Testcontainers bổ sung công cụ cho các lớp service và tích hợp. Mỗi lớp nên kiểm tra đúng ranh giới của nó để bài kiểm thử nhanh, ổn định và chỉ ra lỗi ở nơi có thể xử lý.

### 1. Bản đồ các lớp kiểm thử

Một cách tổ chức thực tế là bắt đầu từ pipeline nhỏ rồi mở rộng dần phạm vi:

~~~text
Kiểm thử toán tử
  Nguồn -> toán tử -> tín hiệu đầu ra
       |
       v
Kiểm thử thành phần
  Service -> Publisher từ dependency giả lập
       |
       v
Kiểm thử tích hợp
  HTTP / Service / Repository / Database thật
~~~

| Lớp | Phạm vi | Dependency | Công cụ thường dùng | Câu hỏi chính |
| --- | --- | --- | --- | --- |
| Toán tử | Một pipeline nhỏ hoặc một toán tử tùy biến | Publisher kiểm soát được | `StepVerifier`, `TestPublisher`, `PublisherProbe` | Tín hiệu và quy tắc demand có đúng không? |
| Thành phần | Một service, handler hoặc adapter | Mock/fake cho dependency bên ngoài | JUnit, Mockito, `StepVerifier` | Thành phần có gọi đúng dependency và phối hợp đúng luồng không? |
| Tích hợp | Nhiều thành phần qua ranh giới thật | Server, database hoặc broker thật/được container hóa | `WebTestClient`, Testcontainers, `StepVerifier` | Cấu hình, giao thức và vòng đời tài nguyên có hoạt động cùng nhau không? |

Không cần đưa mọi trường hợp vào kiểm thử tích hợp. Một lỗi toán tử nên được tái hiện bằng pipeline nhỏ; một quy tắc phối hợp service nên được kiểm tra bằng dependency có thể kiểm soát; chỉ kiểm tra với hệ thống thật khi hợp đồng giữa các thành phần là điều cần xác minh.

### 2. Kiểm thử toán tử với StepVerifier

`StepVerifier` đăng ký vào Publisher và cho phép mô tả chuỗi tín hiệu mong đợi. Đây là công cụ chính để kiểm tra `Mono` và `Flux` mà không phải tự viết subscriber.

Ví dụ kiểm tra `map`, `filter` và completion:

~~~java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

Flux<Integer> result =
    Flux.just(1, 2, 3, 4)
        .filter(value -> value % 2 == 0)
        .map(value -> value * 10);

StepVerifier.create(result)
    .expectNext(20, 40)
    .verifyComplete();
~~~

Kiểm thử xác minh hai phần tử còn lại sau filter, giá trị sau map và tín hiệu hoàn tất. Nếu pipeline phát thêm phần tử, thiếu phần tử hoặc kết thúc bằng lỗi, bước xác minh sẽ thất bại.

Với `Mono`, có thể kiểm tra cả trường hợp có giá trị và hoàn tất rỗng:

~~~java
StepVerifier.create(Mono.just("reactive"))
    .expectNext("reactive")
    .verifyComplete();

StepVerifier.create(Mono.<String>empty())
    .verifyComplete();
~~~

Một `Mono` có thể phát tối đa một phần tử. Vì vậy, kiểm thử cần phân biệt rõ `Mono.empty()` với `Mono.error(...)`; hai trường hợp có thể dẫn đến hành vi nghiệp vụ khác nhau.

### 3. Kiểm tra tín hiệu lỗi và phục hồi

Publisher có hai terminal signal: `onComplete` và `onError`. Cancellation là yêu cầu từ subscriber thông qua Subscription để ngừng tiêu thụ. Một subscription chỉ có thể kết thúc theo một trong các cách phù hợp với vòng đời của nó. Khi kiểm thử lỗi, hãy xác minh loại lỗi hoặc kiểu exception cụ thể thay vì chỉ xác nhận rằng “có lỗi”.

~~~java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

Mono<String> result =
    Mono.<String>error(new IllegalArgumentException("invalid id"))
        .onErrorResume(
            IllegalArgumentException.class,
            error -> Mono.just("fallback")
        );

StepVerifier.create(result)
    .expectNext("fallback")
    .verifyComplete();
~~~

Ví dụ xác minh lỗi gốc được phục hồi thành giá trị dự phòng và downstream hoàn tất bình thường. Nếu muốn kiểm tra lỗi vẫn được truyền ra ngoài:

~~~java
StepVerifier.create(
        Mono.error(new IllegalStateException("database unavailable"))
    )
    .expectError(IllegalStateException.class)
    .verify();
~~~

Các bước hữu ích gồm `expectError(Class)`, `expectErrorMatches(...)` và `expectErrorMessage(...)`. Chọn mức kiểm tra phù hợp với hợp đồng: kiểm tra kiểu exception thường bền vững hơn so với phụ thuộc toàn bộ nội dung message.

### 4. Kiểm tra demand và backpressure

Với Publisher tuân theo Reactive Streams, subscriber chỉ nhận phần tử theo demand đã yêu cầu. `StepVerifier.create(publisher, initialRequest)` cho phép bắt đầu với demand xác định, sau đó tăng demand bằng `thenRequest(n)`.

~~~java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

StepVerifier.create(Flux.range(1, 5), 0)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(1, 2)
    .thenRequest(1)
    .expectNext(3)
    .thenCancel()
    .verify();
~~~

Kiểm thử bắt đầu với demand bằng không, yêu cầu hai phần tử, rồi yêu cầu thêm một phần tử và cuối cùng hủy subscription. Cách này giúp xác minh pipeline không phát dữ liệu vượt quá nhu cầu của subscriber.

Đừng chỉ kiểm tra số lượng phần tử cuối cùng khi backpressure là một phần quan trọng của hợp đồng. Hãy kiểm tra thời điểm yêu cầu, số phần tử được phát sau mỗi lần request và hành vi khi cancellation xảy ra.

### 5. Kiểm tra cancellation và cleanup

Cancellation thường xuất hiện khi client ngắt kết nối, timeout xảy ra hoặc downstream không còn cần dữ liệu. Với nguồn có tài nguyên, cần xác minh việc hủy subscription kích hoạt cleanup phù hợp.

~~~java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertTrue;

AtomicBoolean cancelled = new AtomicBoolean();

StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofMillis(100))
            .doOnCancel(() -> cancelled.set(true))
    )
    .expectSubscription()
    .thenAwait(Duration.ofMillis(100))
    .expectNext(0L)
    .thenCancel()
    .verify();

assertTrue(cancelled.get());
~~~

`doOnCancel` chỉ quan sát cancellation; với tài nguyên thật, hãy kiểm tra hành vi đóng connection, dừng listener hoặc giải phóng handle theo API nguồn.

Cancellation không rollback side effect đã hoàn tất. Bài kiểm thử nên xác minh đúng điều có thể cam kết: ngăn công việc tiếp tục khi nguồn hỗ trợ, gọi cleanup và không phát thêm dữ liệu sau khi subscriber đã hủy.

### 6. Dùng TestPublisher để điều khiển nguồn

`TestPublisher` cho phép bài kiểm thử chủ động phát `onNext`, `onError` hoặc `onComplete`. Nó hữu ích khi cần kiểm tra pipeline trong các tình huống mà nguồn thật khó tái hiện, ví dụ phần tử đến theo từng đợt, lỗi xảy ra sau một số phần tử hoặc nguồn chưa hoàn tất.

~~~java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

TestPublisher<Integer> source = TestPublisher.create();

Flux<Integer> result =
    source.flux()
        .map(value -> value * 10)
        .filter(value -> value >= 20);

StepVerifier.create(result)
    .then(() -> source.next(1, 2))
    .expectNext(20)
    .then(() -> source.next(3))
    .expectNext(30)
    .then(source::complete)
    .verifyComplete();
~~~

Bài kiểm thử chủ động phát từng đợt và xác minh tín hiệu downstream sau mỗi đợt. Nó không phụ thuộc timer hoặc mạng nên dễ tái lập.

Có thể phát lỗi sau một phần tử:

~~~java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.flux())
    .then(() -> source.next("first"))
    .expectNext("first")
    .then(() -> source.error(new IllegalStateException("source failed")))
    .expectErrorMessage("source failed")
    .verify();
~~~

Không nên dùng `TestPublisher` để thay thế mọi nguồn thật. Nó kiểm tra cách pipeline phản ứng với tín hiệu; hành vi của driver, HTTP client hoặc database vẫn cần được kiểm tra ở lớp tích hợp.

### 7. Dùng PublisherProbe để xác minh nhánh được chọn

Một số pipeline có nhánh fallback hoặc nhánh chỉ được gọi trong điều kiện cụ thể. Chỉ kiểm tra giá trị đầu ra đôi khi chưa đủ để chứng minh nhánh mong muốn đã được subscribe. `PublisherProbe` cho phép quan sát subscription, request và cancellation của Publisher được bọc.

~~~java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

PublisherProbe<String> fallback =
    PublisherProbe.of(Mono.just("cached value"));

Mono<String> result =
    remoteClient.fetch()
        .onErrorResume(error -> fallback.mono());

StepVerifier.create(result)
    .expectNext("cached value")
    .verifyComplete();

fallback.assertWasSubscribed();
fallback.assertWasRequested();
~~~

Ví dụ giả định `remoteClient.fetch()` phát lỗi. Bài kiểm thử xác minh fallback được subscribe và có demand. Nếu remote thành công, fallback không nên được subscribe; khi đó có thể dùng `assertWasNotSubscribed()` để kiểm tra nhánh không được chọn.

`PublisherProbe` đặc biệt hữu ích cho `switchIfEmpty`, `onErrorResume` và các nhánh điều kiện. Nó kiểm tra đường đi thực tế của pipeline mà không cần thêm biến đếm mutable vào mã production.

### 8. Kiểm thử thời gian bằng virtual time

Các toán tử như `delay`, `interval`, `timeout` và `retry` có backoff có thể làm bài kiểm thử chậm nếu chờ đồng hồ thật. `StepVerifier.withVirtualTime` cho phép tiến thời gian mô phỏng:

~~~java
import java.time.Duration;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1)).take(3)
    )
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(3))
    .expectNext(0L, 1L, 2L)
    .verifyComplete();
~~~

Pipeline phải được tạo bên trong supplier truyền cho `withVirtualTime`, để scheduler ảo được cài đặt trước khi các toán tử thời gian được lắp ghép. Nếu tạo Publisher trước supplier, một toán tử có thể đã giữ scheduler thật.

Virtual time chỉ điều khiển các toán tử dùng scheduler mà cơ chế kiểm thử thay thế hoặc scheduler ảo được truyền trực tiếp. Nó không tua `Thread.sleep`, I/O blocking hoặc timer của một thư viện bên ngoài Reactor. Với mã nghiệp vụ đọc thời gian hiện tại, hãy inject `java.time.Clock` để kiểm soát thời điểm riêng biệt với scheduler.

### 9. Kiểm thử thành phần: service với dependency giả lập

Kiểm thử thành phần tập trung vào một service hoặc handler. Các dependency bên ngoài như repository và HTTP client có thể được mock để bài kiểm thử kiểm soát được giá trị, lỗi và thời điểm hoàn tất.

Ví dụ service chuyển Order thành OrderView:

~~~java
class OrderService {
    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    Mono<OrderView> findView(String id) {
        return repository.findById(id)
            .map(order -> new OrderView(order.id(), order.status()));
    }
}
~~~

Kiểm thử bằng Mockito và StepVerifier:

~~~java
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

Order order = new Order("42", "PAID");
OrderRepository repository = mock(OrderRepository.class);
when(repository.findById("42")).thenReturn(Mono.just(order));

OrderService service = new OrderService(repository);

StepVerifier.create(service.findView("42"))
    .expectNextMatches(view ->
        view.id().equals("42") && view.status().equals("PAID")
    )
    .verifyComplete();

verify(repository).findById("42");
~~~

Kiểm thử xác minh cả dữ liệu đầu ra lẫn việc service gọi đúng repository. Vì Publisher lazy, lời gọi repository có thể chỉ xảy ra khi subscription; StepVerifier tạo subscription để kích hoạt pipeline.

Nên có thêm trường hợp repository trả `Mono.empty()`, phát lỗi và phục hồi bằng cache hoặc giá trị dự phòng. Mỗi trường hợp nên phản ánh một quy tắc nghiệp vụ cụ thể.

### 10. Mock Publisher đúng cách

Khi mock một phương thức reactive, hãy trả về Publisher phù hợp với hợp đồng:

| Hành vi dependency | Giá trị mock |
| --- | --- |
| Tìm thấy một bản ghi | `Mono.just(value)` |
| Không tìm thấy | `Mono.empty()` |
| Gặp lỗi | `Mono.error(exception)` |
| Trả về nhiều phần tử | `Flux.just(a, b)` hoặc `Flux.fromIterable(values)` |
| Không có dữ liệu và chỉ hoàn tất | `Mono.empty()` hoặc `Mono<Void>` tùy hợp đồng |

Tránh trả `null` từ mock cho một phương thức có hợp đồng trả Publisher. `null` không phải tín hiệu reactive và thường tạo `NullPointerException` trước khi pipeline có thể phát `onError`.

Mock cũng không nên giả lập quá nhiều chi tiết nội bộ của Reactor. Nếu mục tiêu là kiểm tra logic chuyển đổi, hãy dùng Publisher đơn giản. Nếu cần điều khiển thời điểm phát hoặc kiểm tra cancellation, cân nhắc `TestPublisher` thay vì tạo nhiều thread và timer trong mock.

### 11. Kiểm thử tích hợp: xác minh ranh giới thật

Kiểm thử tích hợp xác minh các thành phần hoạt động cùng nhau qua ranh giới mà mock không thể mô phỏng đầy đủ. Ví dụ:

- Controller và bộ chuyển đổi HTTP có serialize/deserialize đúng không?
- Filter, security và exception handler có phối hợp đúng không?
- R2DBC driver và database có thực hiện truy vấn, transaction và rollback đúng không?
- Pool có lấy/trả connection đúng và timeout khi cạn tài nguyên không?
- Client ngắt kết nối có dẫn đến cancellation và cleanup thực tế không?

Với endpoint WebFlux, `WebTestClient` kiểm tra hợp đồng HTTP:

~~~java
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient client =
    WebTestClient.bindToController(new OrderController(orderService))
        .build();

client.get()
    .uri("/orders/42")
    .exchange()
    .expectStatus().isOk()
    .expectBody()
    .jsonPath("$.id").isEqualTo("42");
~~~

`bindToController` phù hợp để kiểm tra controller và mapping cơ bản. Khi cần xác minh filter, security, codec hoặc cấu hình ứng dụng, hãy bind tới application context hoặc khởi động server trên cổng ngẫu nhiên. Khi đó bài kiểm thử bao phủ nhiều cấu hình thật hơn.

### 12. Tích hợp với database thật

Mock repository không thể chứng minh SQL, mapping kiểu dữ liệu, transaction manager hoặc driver R2DBC hoạt động đúng. Với những hợp đồng này, dùng database thật trong môi trường kiểm thử, thường thông qua Testcontainers.

Một bài kiểm thử tích hợp có thể thực hiện các bước:

1. Khởi động database container với phiên bản tương thích môi trường triển khai.
2. Cấu hình `ConnectionFactory` và connection pool trỏ tới container.
3. Chạy migration/schema cần thiết.
4. Gọi service hoặc endpoint thật để tạo và đọc dữ liệu.
5. Xác minh kết quả, transaction rollback và việc giải phóng connection.
6. Dừng container sau khi hoàn tất.

Ví dụ khung cấu hình với PostgreSQL Testcontainers:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class OrderRepositoryIntegrationTest {
    @Container
    static final PostgreSQLContainer<?> database =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.r2dbc.url", () ->
            "r2dbc:postgresql://" + database.getHost() + ":"
                + database.getFirstMappedPort() + "/"
                + database.getDatabaseName()
        );
        registry.add("spring.r2dbc.username", database::getUsername);
        registry.add("spring.r2dbc.password", database::getPassword);
    }

    @Test
    void savesAndLoadsOrder() {
        // Gọi repository/service thật và xác minh bằng StepVerifier.
    }
}
~~~

Đây là khung minh họa; dự án cần có dependency Testcontainers tương ứng, cấu hình driver R2DBC và migration. Không dùng mock cho phần cần chứng minh hành vi SQL hoặc transaction của database thật.

### 13. Phân biệt kiểm thử tích hợp với kiểm thử end-to-end

Kiểm thử tích hợp thường tập trung vào một ranh giới hoặc nhóm thành phần, ví dụ service + repository + database. Kiểm thử end-to-end đi qua gần như toàn bộ hệ thống từ giao diện hoặc HTTP entry point đến các dependency quan trọng.

| Loại kiểm thử | Mục tiêu | Phạm vi điển hình |
| --- | --- | --- |
| Unit/operator | Xác minh quy tắc cục bộ | Một pipeline hoặc class |
| Component | Xác minh phối hợp trong một thành phần | Service + mock/fake dependency |
| Integration | Xác minh hợp đồng giữa thành phần thật | WebFlux + database, repository + driver |
| End-to-end | Xác minh luồng nghiệp vụ xuyên hệ thống | HTTP entry point đến database/broker/dịch vụ phụ thuộc |

End-to-end có giá trị cho luồng nghiệp vụ quan trọng, nhưng thường chậm và nhạy với môi trường. Hãy giữ số lượng vừa đủ, còn phần lớn nhánh lỗi và trường hợp biên nên được kiểm tra ở lớp toán tử hoặc thành phần.

### 14. Tránh kiểm thử reactive không xác định

Một bài kiểm thử không xác định (flaky) có thể lúc qua lúc thất bại do thread, thời gian hoặc tài nguyên dùng chung. Những nguyên nhân thường gặp:

| Nguyên nhân | Vì sao gây flaky | Cách xử lý |
| --- | --- | --- |
| Dùng `Thread.sleep` để đợi tín hiệu | Phụ thuộc tải máy và lịch thread | Dùng `StepVerifier` và virtual time |
| Gọi `subscribe()` thủ công trong test rồi kiểm tra ngay | Test không chờ terminal signal | Dùng `StepVerifier.verify...()` |
| Dùng scheduler dùng chung có trạng thái rò rỉ | Test ảnh hưởng lẫn nhau | Inject scheduler riêng và dispose khi xong |
| Dùng database dùng chung mà không cô lập dữ liệu | Test chạy song song có thể xung đột | Dùng dữ liệu riêng, transaction hoặc container riêng |
| Mock trả `null` | Không tuân theo hợp đồng Publisher | Trả `Mono.empty()`, `Mono.error()` hoặc Flux phù hợp |
| Chỉ kiểm tra giá trị, bỏ qua terminal signal | Lỗi có thể xảy ra sau phần tử cuối | Xác minh `verifyComplete()` hoặc `expectError...()` |
| Không kiểm tra cancellation/cleanup | Tài nguyên có thể rò rỉ sau test | Kiểm tra hook hoặc tài nguyên được đóng |

Không dùng timeout dài để che giấu bài kiểm thử bị treo. Hãy xác định nguồn nào chưa phát terminal signal, scheduler nào chưa được điều khiển hoặc tài nguyên nào chưa được giải phóng.

### 15. Tổ chức test suite theo hợp đồng

Một test suite dễ bảo trì nên đặt tên theo hành vi nghiệp vụ và tín hiệu cần xác minh. Ví dụ:

- `returnsOrderWhenRepositoryFindsOne`
- `completesEmptyWhenOrderDoesNotExist`
- `mapsDatabaseFailureToServiceError`
- `usesCacheWhenRemoteLookupFails`
- `cancelsEventSourceWhenClientStopsConsuming`
- `rollsBackOrderWhenInventoryReservationFails`

Tên test mô tả điều quan sát được thay vì tên toán tử nội bộ. Khi triển khai thay đổi từ `flatMap` sang `concatMap` nhưng hợp đồng nghiệp vụ vẫn giữ nguyên, bài kiểm thử vẫn có ý nghĩa.

Nên chia fixture và helper theo phạm vi. Test helper cho `StepVerifier` không nên che mất phần tử hoặc terminal signal đang được kiểm tra. Với integration test, tạo dữ liệu có khóa riêng và dọn dẹp rõ ràng để có thể chạy lại độc lập.

### 16. Quy trình chọn lớp kiểm thử

Khi thêm một tính năng reactive, hãy lần lượt đặt câu hỏi:

1. Quy tắc nào chỉ liên quan đến một toán tử hoặc một pipeline nhỏ? Kiểm tra bằng `StepVerifier`.
2. Nguồn cần điều khiển từng tín hiệu hay nhánh fallback cần được quan sát? Dùng `TestPublisher` hoặc `PublisherProbe`.
3. Service có phối hợp đúng dependency, lỗi và kết quả rỗng không? Viết component test với mock/fake Publisher.
4. Hành vi nào phụ thuộc driver, transaction, codec hoặc server configuration? Viết integration test với thành phần thật.
5. Luồng nghiệp vụ quan trọng nào cần xác minh xuyên hệ thống? Bổ sung một số end-to-end test.
6. Có timer, scheduler, demand hoặc cancellation nào cần kiểm tra riêng không?
7. Bài kiểm thử có xác minh terminal signal và cleanup hay chỉ kiểm tra giá trị?

Trong module REACTIVE_PROGRAMMING, phân lớp kiểm thử giúp xác minh pipeline từ quy tắc toán tử đến hành vi ứng dụng. `StepVerifier` kiểm tra hợp đồng tín hiệu; `TestPublisher` và `PublisherProbe` kiểm soát nguồn và nhánh; mock/fake giúp kiểm tra phối hợp service; còn `WebTestClient` và database container xác minh các ranh giới tích hợp. Chọn đúng lớp cho từng câu hỏi giúp test suite nhanh, dễ chẩn đoán và bảo vệ đúng các cam kết về dữ liệu, lỗi, backpressure và vòng đời subscription.
