# Kiểm thử OPEN không thực thi Supplier hoặc Publisher gốc

Khi Circuit Breaker ở trạng thái OPEN, lời gọi mới phải bị từ chối trước khi thực thi công việc đến dependency. Với API đồng bộ, Supplier gốc không được gọi. Với API reactive, Publisher gốc không được subscribe. Nếu ứng dụng cấu hình fallback, fallback vẫn được thực thi để tạo kết quả thay thế cho caller.

Đây là một bất biến quan trọng cần kiểm chứng trong Spring Cloud CircuitBreaker: khi mạch đã mở, request không được tiếp tục đi đến dịch vụ phụ thuộc. Một bài kiểm thử chỉ xác nhận caller nhận được fallback là chưa đủ. Fallback có thể được trả về trong khi code gốc vẫn vô tình chạy nếu chuỗi xử lý được lắp sai. Bài kiểm thử cần quan sát trực tiếp số lần gọi Supplier, số lần subscribe Publisher và, khi có thể, số HTTP request thực sự được gửi.

## 1. Hành vi cần xác nhận ở trạng thái OPEN

Circuit Breaker có ba trạng thái chính:

- **CLOSED**: cho phép lời gọi đi đến dependency và ghi nhận kết quả.
- **OPEN**: từ chối nhanh lời gọi mới. Công việc gốc không được thực thi.
- **HALF_OPEN**: cho phép một số lời gọi thăm dò để kiểm tra dependency đã phục hồi hay chưa.

Bài kiểm thử này tập trung vào OPEN. Khi một lời gọi đi qua Circuit Breaker đang OPEN:

1. Circuit Breaker kiểm tra trạng thái trước khi gọi công việc gốc.
2. Lời gọi bị từ chối bằng lỗi như CallNotPermittedException trong Resilience4j.
3. Nếu có fallback, hàm fallback được gọi để tạo kết quả thay thế.
4. Supplier gốc không được thực thi; với reactive, Publisher gốc không được subscribe.
5. Không có request mới được gửi đến HTTP client từ lời gọi bị từ chối.

Có thể biểu diễn bằng sơ đồ:

~~~mermaid
flowchart TD
    A[Caller gọi qua Circuit Breaker] --> B{Trạng thái breaker}
    B -- CLOSED --> C[Thực thi Supplier hoặc subscribe Publisher]
    B -- HALF_OPEN --> D[Cho phép lời gọi thăm dò nếu còn permit]
    B -- OPEN --> E[Từ chối lời gọi]
    E --> F{Có fallback?}
    F -- Có --> G[Thực thi fallback]
    F -- Không --> H[Phát CallNotPermittedException]
    G --> I[Trả kết quả thay thế]
    C --> J[Kết quả từ dependency]
    D --> J
~~~

Điểm cần phân biệt: OPEN ngăn công việc gốc, không ngăn toàn bộ code của request. Fallback, logging, metric và xử lý lỗi vẫn có thể chạy. Vì vậy, assertion phải nhắm vào Supplier hoặc Publisher gốc, không nên kỳ vọng mọi bộ đếm đều bằng không.

## 2. Phân biệt Supplier đồng bộ và Publisher reactive

Hai API có cách xác định công việc gốc đã chạy khác nhau:

| Kiểu lời gọi | Đơn vị được Circuit Breaker bảo vệ | Cách chứng minh không chạy |
|---|---|---|
| Đồng bộ | Supplier<T> | Bộ đếm trong Supplier vẫn bằng 0 |
| Reactive | Mono<T> hoặc Flux<T> | Bộ đếm trong defer vẫn bằng 0, chứng minh Publisher không được subscribe |
| HTTP client | Lời gọi tạo request trong Supplier hoặc Publisher | Server giả lập không nhận request nào |

Với Supplier, chỉ cần đặt bộ đếm bên trong lambda được truyền cho run. Nếu breaker OPEN, lambda đó không được gọi.

Với Reactor, Publisher thường lazy: việc tạo Mono hoặc Flux không đồng nghĩa phần công việc bên trong đã chạy. Để kiểm tra chính xác thời điểm thực thi, dùng Mono.defer hoặc Flux.defer và tăng bộ đếm khi factory của Publisher được gọi. Nếu breaker OPEN, Publisher gốc không được subscribe nên bộ đếm vẫn bằng 0.

Không nên đặt side effect cần kiểm tra bên ngoài Supplier hoặc bên ngoài defer. Code đặt bên ngoài có thể chạy trước khi Circuit Breaker kiểm tra trạng thái và làm bài test đưa ra kết luận sai.

## 3. Chuẩn bị test với Resilience4j

Khi Spring Cloud CircuitBreaker dùng implementation Resilience4j, có thể lấy Circuit Breaker core từ CircuitBreakerRegistry để điều khiển trạng thái trong test.

Các thành phần thường cần:

- Spring Cloud CircuitBreaker starter cho Resilience4j.
- CircuitBreakerFactory cho API đồng bộ.
- ReactiveCircuitBreakerFactory cho API reactive.
- CircuitBreakerRegistry để truy cập instance Resilience4j tương ứng.
- JUnit 5 và AssertJ để viết assertion.
- Reactor Test để kiểm tra Mono hoặc Flux.

Ví dụ dependency Maven cho ứng dụng dùng cả API đồng bộ và reactive cần được chọn theo starter tương ứng. Với phần reactive, dùng starter Reactor Resilience4j; với phần đồng bộ, dùng starter Resilience4j thông thường. Quản lý phiên bản qua Spring Cloud BOM tương thích với Spring Boot của dự án.

Điều quan trọng trong test tích hợp là factory và registry phải sử dụng cùng một CircuitBreakerRegistry. Nếu test điều khiển một registry khác với registry mà factory dùng, việc chuyển trạng thái OPEN sẽ không tác động đến breaker được gọi trong test.

## 4. Mở Circuit Breaker một cách xác định trong test

Không nhất thiết phải gửi nhiều request lỗi và chờ bộ đếm đạt ngưỡng mỗi lần kiểm thử hành vi OPEN. Để kiểm tra riêng bất biến OPEN không gọi công việc gốc, có thể chuyển breaker sang OPEN trực tiếp.

Resilience4j cung cấp thao tác chuyển trạng thái:

~~~java
coreBreaker.transitionToOpenState();
~~~

Ví dụ lấy instance theo ID:

~~~java
String breakerId = "inventory-open-supplier-test";

org.springframework.cloud.client.circuitbreaker.CircuitBreaker springBreaker =
        circuitBreakerFactory.create(breakerId);

io.github.resilience4j.circuitbreaker.CircuitBreaker coreBreaker =
        circuitBreakerRegistry.circuitBreaker(breakerId);

coreBreaker.transitionToOpenState();
~~~

Hãy tạo wrapper từ factory trước, sau đó lấy cùng ID từ registry và chuyển instance đó sang OPEN. Cách này giúp test điều khiển đúng breaker mà Spring Cloud CircuitBreaker sẽ sử dụng, với điều kiện registry được inject là registry của implementation đang hoạt động.

Dùng ID riêng cho từng test hoặc reset trạng thái sau test để không làm ảnh hưởng test khác. Nên xác nhận trạng thái là OPEN ngay trước khi gọi run.

Việc chuyển trạng thái trực tiếp phù hợp với test đơn vị hoặc test tích hợp cho hành vi từ chối. Một test khác có thể kiểm tra toàn bộ quá trình CLOSED chuyển OPEN do failure rate đạt ngưỡng. Hai mục tiêu đó nên được tách để test không phụ thuộc vào thời gian và số request ngoài ý muốn.

## 5. Kiểm thử Supplier gốc không được gọi

Ví dụ dưới đây dùng Spring Cloud CircuitBreaker đồng bộ. Bộ đếm supplierCalls chỉ tăng nếu Supplier gốc thực sự được thực thi.

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;

import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class OpenSupplierCircuitBreakerTest {

    private static final String BREAKER_ID =
            "inventory-open-supplier-test";

    @Autowired
    CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    @Autowired
    CircuitBreakerRegistry circuitBreakerRegistry;

    @Test
    void openBreakerDoesNotInvokeOriginalSupplier() {
        CircuitBreaker springBreaker =
                circuitBreakerFactory.create(BREAKER_ID);

        io.github.resilience4j.circuitbreaker.CircuitBreaker coreBreaker =
                circuitBreakerRegistry.circuitBreaker(BREAKER_ID);

        coreBreaker.transitionToOpenState();

        assertThat(coreBreaker.getState())
                .isEqualTo(
                        io.github.resilience4j.circuitbreaker.CircuitBreaker.State.OPEN);

        AtomicInteger supplierCalls = new AtomicInteger();
        AtomicInteger fallbackCalls = new AtomicInteger();

        String result = springBreaker.run(
                () -> {
                    supplierCalls.incrementAndGet();
                    return "inventory-from-remote";
                },
                error -> {
                    fallbackCalls.incrementAndGet();
                    return "inventory-fallback";
                }
        );

        assertThat(result).isEqualTo("inventory-fallback");
        assertThat(supplierCalls.get()).isZero();
        assertThat(fallbackCalls.get()).isEqualTo(1);
        assertThat(coreBreaker.getState())
                .isEqualTo(
                        io.github.resilience4j.circuitbreaker.CircuitBreaker.State.OPEN);
    }
}
~~~

Các assertion chứng minh ba điều khác nhau:

- Caller nhận kết quả fallback.
- Supplier gốc không chạy, vì supplierCalls vẫn bằng 0.
- Fallback chạy đúng một lần.

Không chỉ kiểm tra result bằng inventory-fallback. Nếu chỉ kiểm tra kết quả, test có thể bỏ sót trường hợp Supplier đã chạy nhưng kết quả sau đó bị thay bằng fallback.

Tên ID cần khớp giữa factory.create và circuitBreakerRegistry.circuitBreaker. Nếu dùng cấu hình riêng theo ID, bảo đảm cấu hình đó được nạp trong test context.

## 6. Kiểm thử khi không khai báo fallback

Nếu không có fallback, lời gọi bị từ chối phải truyền lỗi về caller. Supplier gốc vẫn không được thực thi.

~~~java
@Test
void openBreakerRejectsCallWithoutInvokingSupplier() {
    CircuitBreaker springBreaker =
            circuitBreakerFactory.create(BREAKER_ID);

    io.github.resilience4j.circuitbreaker.CircuitBreaker coreBreaker =
            circuitBreakerRegistry.circuitBreaker(BREAKER_ID);

    coreBreaker.transitionToOpenState();

    AtomicInteger supplierCalls = new AtomicInteger();

    org.assertj.core.api.Assertions.assertThatThrownBy(() ->
            springBreaker.run(() -> {
                supplierCalls.incrementAndGet();
                return "remote";
            })
    ).satisfies(error ->
            assertThat(hasCause(
                    error,
                    io.github.resilience4j.circuitbreaker.CallNotPermittedException.class
            )).isTrue());

    assertThat(supplierCalls.get()).isZero();
}
~~~

Helper hasCause có thể duyệt cause chain nếu adapter bọc exception:

~~~java
private static boolean hasCause(
        Throwable error,
        Class<? extends Throwable> expectedType) {

    Throwable current = error;

    while (current != null) {
        if (expectedType.isInstance(current)) {
            return true;
        }

        Throwable next = current.getCause();
        if (next == current) {
            break;
        }
        current = next;
    }

    return false;
}
~~~

Trong một số adapter, exception có thể được truyền trực tiếp; trong adapter khác, nó có thể được bọc. Kiểm tra theo cause chain giúp assertion tập trung vào nguyên nhân từ chối thực tế thay vì phụ thuộc wrapper cụ thể.

Nếu API hoặc phiên bản đang dùng có overload khác, hãy giữ nguyên mục tiêu kiểm thử: lỗi từ chối được truyền ra caller và bộ đếm Supplier gốc bằng 0.

## 7. Kiểm thử Publisher gốc không được subscribe

Với reactive Circuit Breaker, việc tạo Mono không chứng minh Publisher đã chạy. Dùng Mono.defer để bộ đếm chỉ tăng khi có subscription vào phần công việc gốc.

~~~java
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;

import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class OpenReactiveCircuitBreakerTest {

    private static final String BREAKER_ID =
            "inventory-open-publisher-test";

    @Autowired
    ReactiveCircuitBreakerFactory<?, ?> reactiveCircuitBreakerFactory;

    @Autowired
    CircuitBreakerRegistry circuitBreakerRegistry;

    @Test
    void openBreakerDoesNotSubscribeToOriginalPublisher() {
        ReactiveCircuitBreaker reactiveBreaker =
                reactiveCircuitBreakerFactory.create(BREAKER_ID);

        io.github.resilience4j.circuitbreaker.CircuitBreaker coreBreaker =
                circuitBreakerRegistry.circuitBreaker(BREAKER_ID);

        coreBreaker.transitionToOpenState();

        assertThat(coreBreaker.getState())
                .isEqualTo(
                        io.github.resilience4j.circuitbreaker.CircuitBreaker.State.OPEN);

        AtomicInteger originalSubscriptions = new AtomicInteger();
        AtomicInteger fallbackSubscriptions = new AtomicInteger();

        Mono<String> originalPublisher = Mono.defer(() -> {
            originalSubscriptions.incrementAndGet();
            return Mono.just("inventory-from-remote");
        });

        Mono<String> protectedPublisher = reactiveBreaker.run(
                originalPublisher,
                error -> Mono.defer(() -> {
                    fallbackSubscriptions.incrementAndGet();
                    return Mono.just("inventory-fallback");
                })
        );

        StepVerifier.create(protectedPublisher)
                .expectNext("inventory-fallback")
                .verifyComplete();

        assertThat(originalSubscriptions.get()).isZero();
        assertThat(fallbackSubscriptions.get()).isEqualTo(1);
        assertThat(coreBreaker.getState())
                .isEqualTo(
                        io.github.resilience4j.circuitbreaker.CircuitBreaker.State.OPEN);
    }
}
~~~

StepVerifier subscribe vào Publisher được bảo vệ. Circuit Breaker đang OPEN nên nó từ chối trước khi subscribe Publisher gốc. Fallback được subscribe và phát ra giá trị thay thế.

Hai bộ đếm có ý nghĩa khác nhau:

- originalSubscriptions bằng 0: không có subscription vào công việc gốc.
- fallbackSubscriptions bằng 1: fallback được chạy đúng một lần.

Nếu đặt originalSubscriptions.incrementAndGet() bên ngoài Mono.defer, bộ đếm sẽ tăng ngay khi tạo Publisher và test không còn đo đúng việc subscribe.

## 8. Kiểm thử Flux theo cùng nguyên tắc

Với Flux, dùng Flux.defer để chỉ tăng bộ đếm khi Publisher gốc được subscribe:

~~~java
AtomicInteger originalSubscriptions = new AtomicInteger();

Flux<String> originalPublisher = Flux.defer(() -> {
    originalSubscriptions.incrementAndGet();
    return Flux.just("item-1", "item-2");
});

Flux<String> protectedPublisher = reactiveBreaker.run(
        originalPublisher,
        error -> Flux.just("fallback-item")
);

StepVerifier.create(protectedPublisher)
        .expectNext("fallback-item")
        .verifyComplete();

assertThat(originalSubscriptions.get()).isZero();
~~~

Kết quả mong đợi giống Mono: khi breaker OPEN, Flux gốc không được subscribe. Fallback Flux có thể được subscribe và phát các phần tử thay thế.

Cần bảo đảm fallback trả đúng kiểu publisher. Mono<T> dùng fallback Mono<T>; Flux<T> dùng fallback Flux<T>. Không đổi kiểu dữ liệu trong test chỉ để làm assertion đơn giản hơn.

## 9. Xác minh không có HTTP request thực sự

Bộ đếm trong Supplier hoặc defer chứng minh code gốc không chạy ở mức ứng dụng. Với bài kiểm thử tích hợp HTTP, có thể dùng MockWebServer hoặc WireMock để xác nhận không có request đến server giả lập.

Ví dụ với WebClient và MockWebServer:

~~~java
MockWebServer server = new MockWebServer();
server.start();

try {
    WebClient webClient = WebClient.builder()
            .baseUrl(server.url("/").toString())
            .build();

    AtomicInteger publisherFactoryCalls = new AtomicInteger();

    Mono<String> original = Mono.defer(() -> {
        publisherFactoryCalls.incrementAndGet();

        return webClient.get()
                .uri("/inventory")
                .retrieve()
                .bodyToMono(String.class);
    });

    Mono<String> protectedCall = reactiveBreaker.run(
            original,
            error -> Mono.just("fallback")
    );

    StepVerifier.create(protectedCall)
            .expectNext("fallback")
            .verifyComplete();

    assertThat(publisherFactoryCalls.get()).isZero();
    assertThat(server.getRequestCount()).isZero();
} finally {
    server.shutdown();
}
~~~

Nếu breaker OPEN, Mono.defer không được thực thi và MockWebServer không nhận request nào. Assertion getRequestCount bằng 0 là bằng chứng ở biên HTTP rằng lời gọi không đi ra khỏi ứng dụng.

Khi dùng WebClient, việc tạo request specification bên ngoài defer thường chưa gửi HTTP vì WebClient reactive lazy. Tuy nhiên, đặt toàn bộ phần tạo và thực thi publisher trong defer làm ranh giới kiểm thử rõ ràng hơn và tránh side effect xảy ra sớm.

Với lời gọi đồng bộ, có thể dùng mock HTTP server tương tự và xác nhận số request bằng 0 sau khi gọi Circuit Breaker đang OPEN.

## 10. Theo dõi event CallNotPermitted

Resilience4j Circuit Breaker có event publisher để quan sát lời gọi bị từ chối khi mạch OPEN. Có thể đăng ký listener trước khi gọi:

~~~java
AtomicInteger rejectedCalls = new AtomicInteger();

coreBreaker.getEventPublisher()
        .onCallNotPermitted(event -> rejectedCalls.incrementAndGet());
~~~

Sau khi gọi qua Spring Cloud CircuitBreaker và xác nhận fallback, có thể kiểm tra:

~~~java
assertThat(rejectedCalls.get()).isEqualTo(1);
~~~

Event này bổ sung bằng chứng rằng Circuit Breaker đã từ chối lời gọi. Tuy nhiên, event không thay thế bộ đếm Supplier hoặc Publisher:

- CallNotPermitted chứng minh breaker từ chối.
- Bộ đếm Supplier bằng 0 chứng minh Supplier gốc không chạy.
- Bộ đếm subscription bằng 0 chứng minh Publisher gốc không được subscribe.
- HTTP request count bằng 0 chứng minh không có request đến server giả lập.

Kết hợp các assertion giúp test kiểm tra cả quyết định của Circuit Breaker lẫn tác động thực tế lên công việc gốc.

## 11. Tránh test không ổn định do thời gian

Không nên dùng Thread.sleep để hy vọng Circuit Breaker chuyển sang OPEN rồi mới gọi. Test dựa trên thời gian dễ chập chờn vì tốc độ máy, scheduler và thời gian chạy của các test khác.

Để kiểm tra riêng hành vi từ chối:

1. Tạo breaker với ID riêng.
2. Lấy đúng instance từ registry mà factory sử dụng.
3. Gọi transitionToOpenState().
4. Xác nhận state hiện tại là OPEN.
5. Gọi Supplier hoặc subscribe Publisher được bảo vệ.
6. Xác nhận fallback hoặc lỗi từ chối.
7. Xác nhận bộ đếm công việc gốc bằng 0.

Nếu cần kiểm thử tự động mở mạch theo failure threshold, hãy viết test riêng với cấu hình cửa sổ nhỏ và số lần gọi lỗi xác định. Test đó kiểm tra state transition; test hiện tại kiểm tra hành vi khi trạng thái đã OPEN.

Tránh dùng chung ID giữa các test chạy song song. Mỗi test có thể vô tình reset hoặc thay đổi trạng thái của test khác nếu cùng sử dụng một registry instance. Dùng ID duy nhất theo test hoặc reset breaker sau khi test kết thúc.

## 12. Phân biệt OPEN và HALF_OPEN trong assertion

Một lỗi phổ biến là kiểm tra không gọi Supplier sau khi đã chờ một khoảng thời gian dài. Khi hết waitDurationInOpenState, Circuit Breaker có thể chuyển từ OPEN sang HALF_OPEN. HALF_OPEN cho phép một số lời gọi thăm dò, nên Supplier hoặc Publisher có thể được thực thi.

Vì vậy, trước assertion cần xác nhận trạng thái chính xác:

~~~java
assertThat(coreBreaker.getState())
        .isEqualTo(
                io.github.resilience4j.circuitbreaker.CircuitBreaker.State.OPEN);
~~~

Không chỉ dựa vào thời điểm gọi hoặc số lần lỗi trước đó. Nếu test chạy đúng lúc chuyển trạng thái, kết quả có thể thay đổi.

Đối với Resilience4j, có thể cấu hình waitDurationInOpenState đủ dài trong môi trường test để giảm nguy cơ trạng thái tự chuyển trong lúc assertion. Dù vậy, vẫn nên dùng ID riêng và thực hiện kiểm tra ngay sau khi chủ động chuyển OPEN.

Ở HALF_OPEN, mục tiêu kiểm thử khác: xác nhận số lời gọi thăm dò được phép và kết quả của chúng quyết định breaker trở về CLOSED hay chuyển lại OPEN. Không dùng assertion Supplier luôn bằng 0 cho HALF_OPEN.

## 13. Những lỗi thường gặp trong bài kiểm thử OPEN

- **Chỉ kiểm tra fallback result**: chưa chứng minh Supplier hoặc Publisher gốc không chạy.
- **Đặt bộ đếm ngoài Supplier**: bộ đếm tăng trước khi Circuit Breaker kiểm tra trạng thái.
- **Dùng Mono.just với side effect đã chạy trước đó**: Publisher có thể đã tạo dữ liệu hoặc gọi hàm eager khi assembly; dùng Mono.defer.
- **Không dùng cùng registry với factory**: test mở một breaker nhưng ứng dụng gọi breaker khác.
- **Không xác nhận state OPEN trước khi gọi**: breaker có thể đã chuyển sang HALF_OPEN.
- **Dùng ID chung giữa các test**: test song song có thể tác động trạng thái lẫn nhau.
- **Fallback gọi lại dependency gốc**: HTTP request vẫn xuất hiện do chính fallback, dù Supplier hoặc Publisher gốc bị chặn.
- **Chỉ đếm event CallNotPermitted**: event xác nhận từ chối nhưng không chứng minh không có side effect ở code khác.
- **Không phân biệt assembly và subscription**: tạo Mono chưa có nghĩa request đã được gửi.
- **Dùng sleep để đồng bộ**: test phụ thuộc tốc độ môi trường và dễ flaky.
- **Quên reset breaker hoặc dùng ID riêng**: state OPEN có thể ảnh hưởng các test chạy sau.
- **Khẳng định HALF_OPEN cũng không thực thi công việc gốc**: HALF_OPEN cho phép lời gọi thăm dò theo cấu hình.

## 14. Quy trình kiểm chứng trong Spring Cloud CircuitBreaker

Khi viết test cho hành vi OPEN, có thể thực hiện theo trình tự:

1. Xác định API đang kiểm thử là synchronous CircuitBreakerFactory hay reactive ReactiveCircuitBreakerFactory.
2. Đảm bảo starter Resilience4j và registry tương ứng được cấu hình trong test context.
3. Tạo breaker qua factory bằng một ID dành riêng cho test.
4. Lấy cùng instance từ CircuitBreakerRegistry và chuyển sang OPEN.
5. Xác nhận state OPEN ngay trước khi gọi.
6. Với synchronous API, tăng bộ đếm bên trong Supplier và gọi run.
7. Với reactive API, đặt bộ đếm bên trong Mono.defer hoặc Flux.defer, rồi dùng StepVerifier subscribe publisher được bảo vệ.
8. Kiểm tra fallback chạy đúng hoặc lỗi CallNotPermittedException được truyền ra.
9. Xác nhận Supplier không được gọi hoặc Publisher gốc không được subscribe.
10. Nếu cần, dùng MockWebServer/WireMock và xác nhận không có HTTP request.
11. Đăng ký event publisher để kiểm tra CallNotPermitted.
12. Dùng ID riêng hoặc reset breaker để cô lập trạng thái giữa các test.

Một bài kiểm thử OPEN đáng tin cậy cần chứng minh cả trạng thái và tác động. State phải là OPEN tại thời điểm gọi; caller nhận fallback hoặc lỗi từ chối; Supplier gốc có số lần gọi bằng 0; Publisher gốc có số lần subscribe bằng 0; và không có HTTP request nào được gửi từ đường thực thi bị chặn. Khi tách rõ công việc gốc với fallback, dùng Mono.defer cho reactive và điều khiển trạng thái bằng registry đúng instance, test sẽ xác nhận chính xác rằng Circuit Breaker ngăn request mới đi đến dependency khi mạch đang OPEN.
