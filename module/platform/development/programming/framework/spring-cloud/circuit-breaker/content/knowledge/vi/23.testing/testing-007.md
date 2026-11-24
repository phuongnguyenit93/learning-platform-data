# Kiểm thử recordExceptions, ignoreExceptions và predicate

Circuit Breaker không chỉ đếm số exception phát sinh. Nó cần phân loại exception để biết lời gọi nào thực sự phản ánh lỗi của dependency, lời gọi nào là kết quả nghiệp vụ bình thường và loại lỗi nào cần được theo dõi theo quy tắc riêng. Resilience4j cung cấp `recordExceptions`, `ignoreExceptions` và các predicate để xác định cách từng exception đi vào sliding window.

Bài này thuộc chương **Kiểm thử** của module `SPRING_CLOUD_CIRCUIT_BREAKER`. Ta sẽ kiểm tra cấu hình phân loại bằng JUnit, xác nhận metric success/failure, kiểm tra ngưỡng chuyển OPEN và bảo đảm lỗi nghiệp vụ không làm sai trạng thái breaker. Các ví dụ dùng Resilience4j trực tiếp để kiểm thử quy tắc phân loại một cách độc lập; sau đó áp dụng cùng cấu hình vào Spring Cloud CircuitBreaker theo ID.

## 1. Vì sao cần kiểm thử cách phân loại exception?

Một dependency có thể trả về nhiều loại kết quả:

- Timeout hoặc lỗi kết nối: dependency không cung cấp được kết quả đúng hạn.
- HTTP 5xx: dependency hoặc gateway gặp lỗi phía máy chủ.
- HTTP 404: tài nguyên không tồn tại, có thể là kết quả nghiệp vụ hợp lệ.
- HTTP 400/422: request không hợp lệ hoặc không thỏa quy tắc nghiệp vụ.
- Lỗi xác thực: credential của ứng dụng gọi có thể hết hạn hoặc thiếu quyền.
- Exception do code cục bộ: lỗi mapping hoặc xử lý ở service gọi.

Nếu mọi exception đều được tính là failure, một đợt request sai hoặc nhiều mã sản phẩm không tồn tại có thể làm breaker mở dù dependency vẫn khỏe. Nếu bỏ qua quá nhiều exception, breaker có thể không phát hiện dependency đang lỗi.

Kiểm thử phân loại cần trả lời bốn câu hỏi:

1. Exception nào được ghi nhận là failure?
2. Exception nào bị bỏ qua hoàn toàn, không tính success hoặc failure?
3. Exception không khớp danh sách hoặc predicate được xem là success hay failure?
4. Sau khi đủ số mẫu, failure rate có làm breaker chuyển OPEN đúng ngưỡng không?

## 2. Phân biệt recordExceptions, ignoreExceptions và predicate

Ba cơ chế có ý nghĩa khác nhau:

| Cấu hình | Khi exception khớp | Ảnh hưởng tới sliding window |
|---|---|---|
| `recordExceptions(A.class)` | Ghi nhận là failure | Tăng số failed calls và số mẫu được ghi nhận |
| `ignoreExceptions(B.class)` | Bỏ qua exception | Không tăng success, failure hoặc số mẫu được ghi nhận |
| `recordException(predicate)` | Predicate trả `true` thì failure; trả `false` thì success | Kết quả phụ thuộc quy tắc boolean |
| `ignoreException(predicate)` | Predicate trả `true` thì bỏ qua | Không tính success hoặc failure |

Có một khác biệt dễ nhầm: khi cấu hình danh sách `recordExceptions`, các exception không nằm trong danh sách được xem là success theo quy tắc mặc định của danh sách đó, trừ khi chúng khớp `ignoreExceptions`. Chúng không tự động bị bỏ qua.

Ngược lại, `ignoreExceptions` loại exception khỏi cả hai phía success và failure. Exception vẫn được truyền về caller; Circuit Breaker chỉ không dùng nó để tính tỷ lệ.

Khi cùng cấu hình record và ignore, quy tắc ignore có ưu tiên: exception được ignore không bị tính là failure dù nó cũng khớp quy tắc record. Với predicate, `ignoreException` cũng là cách loại trừ trước khi quyết định ghi nhận failure. Vì vậy, hãy kiểm thử cả trường hợp exception có thể khớp nhiều quy tắc.

## 3. Cấu hình recordExceptions và ignoreExceptions bằng Java

Ví dụ dịch vụ Catalog có các loại exception:

- `RemoteTimeoutException`: timeout khi gọi Catalog Service, cần tính failure.
- `RemoteServerException`: lỗi server từ dependency, cần tính failure.
- `ProductNotFoundException`: sản phẩm không tồn tại, là kết quả nghiệp vụ nên bỏ qua.
- `BusinessRuleException`: request không thỏa điều kiện nghiệp vụ, nên bỏ qua.

Có thể cấu hình như sau:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig.SlidingWindowType;

CircuitBreakerConfig config = CircuitBreakerConfig.custom()
    .slidingWindowType(SlidingWindowType.COUNT_BASED)
    .slidingWindowSize(10)
    .minimumNumberOfCalls(5)
    .failureRateThreshold(50)
    .recordExceptions(
        RemoteTimeoutException.class,
        RemoteServerException.class
    )
    .ignoreExceptions(
        ProductNotFoundException.class,
        BusinessRuleException.class
    )
    .build();
~~~

Trong cấu hình này:

- Timeout và lỗi server được ghi nhận là failure.
- Sản phẩm không tồn tại và lỗi nghiệp vụ bị bỏ qua.
- Exception không thuộc danh sách record được xem là success, nếu không bị ignore.
- Breaker chỉ tính failure rate sau khi đã có tối thiểu năm mẫu được ghi nhận.

Cấu hình `recordExceptions` phù hợp khi ứng dụng muốn khai báo rõ các loại lỗi được tính vào failure. Hãy lập danh sách đủ rộng để bao phủ các lỗi hạ tầng có thể phát sinh. Nếu một exception mới không nằm trong danh sách, nó có thể bị tính là success và che khuất sự cố.

Nếu mục tiêu là mặc định xem mọi exception là failure và chỉ loại trừ một vài lỗi nghiệp vụ, có thể chỉ cấu hình `ignoreExceptions`. Đây thường là lựa chọn ngắn gọn khi số exception cần bỏ qua ít và đã được phân loại rõ.

## 4. Dùng predicate để phân loại theo điều kiện

Danh sách class phù hợp khi loại lỗi đã biết trước. Predicate hữu ích khi cần kiểm tra thuộc tính của exception, chẳng hạn HTTP status, mã lỗi hoặc loại nguyên nhân bên trong.

Ví dụ, chỉ xem lỗi từ HTTP 5xx là failure, bỏ qua lỗi không tìm thấy và các lỗi nghiệp vụ:

~~~java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
    .slidingWindowType(SlidingWindowType.COUNT_BASED)
    .slidingWindowSize(20)
    .minimumNumberOfCalls(10)
    .failureRateThreshold(50)
    .recordException(exception ->
        exception instanceof RemoteCallException remote
            && remote.statusCode() >= 500
    )
    .ignoreException(exception ->
        exception instanceof ProductNotFoundException
            || exception instanceof BusinessRuleException
    )
    .build();
~~~

Trong ví dụ:

- `RemoteCallException(503)` được ghi nhận là failure.
- `RemoteCallException(404)` không khớp record predicate nên được tính là success.
- `ProductNotFoundException` bị ignore nên không tính success hoặc failure.
- Các exception khác không khớp record predicate được xem là success, trừ khi bị ignore.

Predicate cần ngắn, xác định và không có side effect. Không thực hiện I/O, truy vấn cơ sở dữ liệu hoặc gọi dịch vụ khác bên trong predicate. Predicate được đánh giá trong đường xử lý kết quả của lời gọi; công việc chậm ở đây có thể làm tăng latency.

Không để predicate ném exception. Hãy kiểm tra null và kiểu exception trước khi đọc thuộc tính, đồng thời dùng các exception nội bộ đã được chuẩn hóa để quy tắc dễ kiểm tra.

## 5. Kiểm thử độc lập bằng JUnit và AssertJ

Có thể tạo Circuit Breaker trực tiếp từ `CircuitBreakerConfig` để kiểm thử quy tắc phân loại mà không cần khởi động toàn bộ Spring context.

Ví dụ helper cho JUnit 5:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig.SlidingWindowType;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class CircuitBreakerExceptionClassificationTest {

    private static void invokeFailure(
            CircuitBreaker circuitBreaker,
            RuntimeException exception) {

        assertThatThrownBy(() ->
            CircuitBreaker.decorateSupplier(
                circuitBreaker,
                () -> {
                    throw exception;
                }
            ).get()
        ).isSameAs(exception);
    }

    private static void invokeSuccess(CircuitBreaker circuitBreaker) {
        String result = CircuitBreaker.decorateSupplier(
            circuitBreaker,
            () -> "ok"
        ).get();

        assertThat(result).isEqualTo("ok");
    }

    // Các exception fixture dùng trong những test ở các phần tiếp theo.
    static class RemoteTimeoutException extends RuntimeException {}
    static class RemoteServerException extends RuntimeException {}
    static class BusinessRuleException extends RuntimeException {}
    static class ProductNotFoundException extends RuntimeException {}

    static class RemoteCallException extends RuntimeException {
        private final int statusCode;

        RemoteCallException(int statusCode) {
            this.statusCode = statusCode;
        }

        int statusCode() {
            return statusCode;
        }
    }
}
~~~

Helper `invokeFailure` xác nhận exception vẫn được truyền tới caller. Circuit Breaker không tự biến exception thành fallback nếu ta chỉ dùng Resilience4j core decorator. Fallback cần được khai báo ở tầng Spring Cloud CircuitBreaker hoặc trong pipeline gọi tương ứng.

Các test nên kiểm tra cả exception truyền ra ngoài lẫn metric bên trong breaker. Chỉ kiểm tra exception bị ném chưa đủ để biết exception được tính là failure, success hay ignored.

## 6. Kiểm thử danh sách record và ignore

Test sau xác nhận ba trường hợp: exception được record, exception bị ignore và exception không nằm trong danh sách record:

~~~java
@Test
void recordAndIgnoreExceptionsHaveDifferentMetricEffects() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowType(SlidingWindowType.COUNT_BASED)
        .slidingWindowSize(10)
        .minimumNumberOfCalls(5)
        .failureRateThreshold(50)
        .recordExceptions(
            RemoteTimeoutException.class,
            BusinessRuleException.class
        )
        .ignoreExceptions(BusinessRuleException.class)
        .build();

    CircuitBreaker breaker = CircuitBreaker.of("catalog-record-test", config);

    invokeFailure(breaker, new RemoteTimeoutException());
    // BusinessRuleException khớp cả record và ignore; ignore phải được ưu tiên.
    invokeFailure(breaker, new BusinessRuleException());
    invokeFailure(breaker, new IllegalStateException("not in record list"));

    assertThat(breaker.getMetrics().getNumberOfFailedCalls()).isEqualTo(1);
    assertThat(breaker.getMetrics().getNumberOfSuccessfulCalls()).isEqualTo(1);
    assertThat(breaker.getMetrics().getNumberOfBufferedCalls()).isEqualTo(2);
}
~~~

Kết quả mong đợi:

- `RemoteTimeoutException` làm số failed calls tăng một.
- `BusinessRuleException` bị ignore nên không nằm trong buffered calls.
- `IllegalStateException` không khớp `recordExceptions`, vì vậy được tính là success.
- Tổng số mẫu được ghi nhận là hai, không phải ba.

Test này rất quan trọng vì nó phát hiện một lỗi cấu hình phổ biến: nhóm phát sinh exception không nằm trong danh sách record bị tính là success ngoài dự kiến. Nếu muốn mọi lỗi không phải nghiệp vụ đều là failure, hãy dùng ignore list phù hợp thay vì record list quá hẹp.

## 7. Kiểm thử predicate theo HTTP status

Predicate cần được kiểm tra bằng nhiều giá trị biên. Ví dụ:

~~~java
@Test
void predicateRecordsServerErrorsAndIgnoresBusinessErrors() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowType(SlidingWindowType.COUNT_BASED)
        .slidingWindowSize(10)
        .minimumNumberOfCalls(5)
        .failureRateThreshold(50)
        .recordException(exception ->
            exception instanceof RemoteCallException remote
                && remote.statusCode() >= 500
        )
        .ignoreException(exception ->
            exception instanceof ProductNotFoundException
        )
        .build();

    CircuitBreaker breaker = CircuitBreaker.of("catalog-predicate-test", config);

    invokeFailure(breaker, new RemoteCallException(503));
    invokeFailure(breaker, new RemoteCallException(404));
    invokeFailure(breaker, new ProductNotFoundException());

    assertThat(breaker.getMetrics().getNumberOfFailedCalls()).isEqualTo(1);
    assertThat(breaker.getMetrics().getNumberOfSuccessfulCalls()).isEqualTo(1);
    assertThat(breaker.getMetrics().getNumberOfBufferedCalls()).isEqualTo(2);
}
~~~

Test xác nhận 503 là failure, 404 không khớp record predicate nên được tính success, còn ProductNotFoundException bị ignore. Hãy bổ sung các trường hợp biên phù hợp với API thực tế, chẳng hạn 429 throttling, 401/403 credential, 408 timeout và các exception do HTTP client tạo ra.

Nếu 429 mang ý nghĩa quota nghiệp vụ thay vì throttling dependency, hãy phân loại theo hợp đồng API. Predicate chỉ nên kiểm tra status sau khi client adapter đã chuyển response thành exception có ý nghĩa; không suy diễn mọi status giống nhau ở mọi dịch vụ.

## 8. Kiểm thử failure rate và chuyển trạng thái OPEN

Kiểm thử phân loại nên được nối với hành vi của Circuit Breaker. Một cấu hình count-based nhỏ giúp test xác định được thời điểm breaker mở:

~~~java
@Test
void recordedFailuresCanOpenTheCircuitBreaker() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowType(SlidingWindowType.COUNT_BASED)
        .slidingWindowSize(4)
        .minimumNumberOfCalls(4)
        .failureRateThreshold(50)
        .recordException(exception ->
            exception instanceof RemoteCallException remote
                && remote.statusCode() >= 500
        )
        .ignoreException(exception ->
            exception instanceof ProductNotFoundException
        )
        .build();

    CircuitBreaker breaker = CircuitBreaker.of("catalog-open-test", config);

    invokeFailure(breaker, new RemoteCallException(503));
    invokeFailure(breaker, new RemoteCallException(502));
    invokeSuccess(breaker);
    invokeSuccess(breaker);

    assertThat(breaker.getMetrics().getNumberOfBufferedCalls()).isEqualTo(4);
    assertThat(breaker.getMetrics().getNumberOfFailedCalls()).isEqualTo(2);
    assertThat(breaker.getMetrics().getFailureRate()).isEqualTo(50.0f);
    assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.OPEN);

    assertThatThrownBy(() ->
        CircuitBreaker.decorateSupplier(breaker, () -> "not called").get()
    ).isInstanceOf(CallNotPermittedException.class);
}
~~~

Hai lỗi server trong bốn mẫu tạo failure rate 50%. Khi đạt minimumNumberOfCalls và chạm failureRateThreshold, breaker chuyển OPEN. Lời gọi tiếp theo bị từ chối bằng `CallNotPermittedException` trước khi supplier chạy.

Trong test thực tế, có thể dùng cấu hình thời gian mở đủ dài để tránh breaker tự chuyển HALF_OPEN trước khi assertion hoàn tất. Không dùng sleep tùy tiện để đồng bộ test; nếu cần kiểm thử thời gian, hãy dùng clock hoặc scheduler có thể kiểm soát theo API được phiên bản Resilience4j hỗ trợ.

## 9. Kiểm tra exception bị ignore không làm tăng số mẫu

Một test riêng giúp xác nhận exception nghiệp vụ vẫn được truyền tới caller nhưng không ảnh hưởng sliding window:

~~~java
@Test
void ignoredExceptionIsPropagatedButNotRecorded() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowSize(10)
        .minimumNumberOfCalls(5)
        .ignoreExceptions(ProductNotFoundException.class)
        .build();

    CircuitBreaker breaker = CircuitBreaker.of("catalog-ignore-test", config);

    invokeFailure(breaker, new ProductNotFoundException());

    assertThat(breaker.getMetrics().getNumberOfFailedCalls()).isZero();
    assertThat(breaker.getMetrics().getNumberOfSuccessfulCalls()).isZero();
    assertThat(breaker.getMetrics().getNumberOfBufferedCalls()).isZero();
    assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.CLOSED);
}
~~~

Đừng kiểm tra duy nhất failure rate bằng 0. Một cửa sổ chưa có mẫu cũng có thể trả về giá trị không xác định hoặc giá trị sentinel tùy API. Kiểm tra số success, failure và buffered calls giúp xác nhận exception thực sự bị bỏ qua.

## 10. Kiểm thử cấu hình qua Spring Cloud CircuitBreaker

Kiểm thử Resilience4j core xác nhận quy tắc phân loại. Ứng dụng còn cần kiểm tra cấu hình đã được gắn vào đúng ID khi dùng Spring Cloud CircuitBreaker.

Ví dụ customizer:

~~~java
@Bean
Customizer<Resilience4JCircuitBreakerFactory> catalogCircuitBreakerConfig() {
    return factory -> factory.configure(builder -> builder
        .circuitBreakerConfig(CircuitBreakerConfig.custom()
            .slidingWindowType(SlidingWindowType.COUNT_BASED)
            .slidingWindowSize(10)
            .minimumNumberOfCalls(5)
            .failureRateThreshold(50)
            .recordExceptions(RemoteTimeoutException.class)
            .ignoreExceptions(ProductNotFoundException.class)
            .build()),
        "catalog-read");
}
~~~

Ở tầng tích hợp, nên dùng Spring Boot test để xác nhận:

- Customizer được Spring nạp.
- Feign client hoặc service gọi đúng ID `catalog-read`.
- Client adapter chuyển HTTP response lỗi thành exception đúng loại.
- Exception nghiệp vụ không làm tăng failure rate.
- Timeout hoặc lỗi server được ghi nhận theo cấu hình.
- Khi breaker OPEN, request mới bị từ chối và fallback được gọi nếu có.

Không chỉ test class cấu hình tồn tại. Một integration test nên gửi request qua client thật trong test, dùng mock HTTP server hoặc stub server để kiểm soát status và timeout. Như vậy test kiểm tra cả ErrorDecoder, exception mapping và Circuit Breaker thay vì chỉ kiểm tra object config.

## 11. Tránh test sai do lỗi không được chuyển thành exception

Circuit Breaker thường phân loại kết quả lỗi dựa trên exception được ném ra từ supplier hoặc Publisher. Nếu HTTP client trả về một object response bình thường có status 500 mà code không ném exception, Circuit Breaker có thể xem invocation là success.

Ví dụ, nếu client adapter trả `RemoteResponse(status=503)` như một giá trị bình thường, `recordExceptions` sẽ không được gọi. Có hai cách xử lý:

- Chuyển response lỗi thành exception có kiểu rõ ràng trước khi kết quả đi qua Circuit Breaker.
- Nếu chủ ý giữ response làm kết quả, dùng cấu hình `recordResult` để phân loại kết quả trả về.

Với WebClient `retrieve()`, các response 4xx/5xx thường được chuyển thành WebClientResponseException nếu không được xử lý thành response bình thường bằng `onStatus`. Với OpenFeign, ErrorDecoder có thể ánh xạ status thành exception nghiệp vụ hoặc RetryableException. Hãy test adapter riêng để xác nhận status thực tế tạo ra exception nào.

## 12. Ma trận test nên có

| Kịch bản | Kết quả phân loại mong đợi | Điều cần assertion |
|---|---|---|
| Remote timeout | Failure | failed calls tăng |
| HTTP 5xx đã ánh xạ thành exception server | Failure | failure rate tăng |
| HTTP 404 thành ProductNotFoundException | Ignored hoặc success theo policy | ignored không tăng buffered calls |
| BusinessRuleException | Ignored | không tăng success/failure |
| Exception không khớp record list | Success khi dùng explicit record list | successful calls tăng |
| Predicate nhận status 503 | Failure | predicate trả true |
| Predicate nhận status 404 | Success nếu không bị ignore | predicate trả false |
| Exception khớp cả record và ignore | Ignored | ignore có ưu tiên |
| Đủ mẫu và failure rate chạm ngưỡng | Breaker OPEN | state chuyển OPEN |
| Lời gọi khi OPEN | Not permitted | supplier không chạy |
| Response lỗi nhưng adapter không ném exception | Có thể bị tính success | integration test phải phát hiện mapping sai |

Mỗi test nên tạo Circuit Breaker instance mới. Không dùng chung registry hoặc breaker giữa các test nếu không reset state và metrics, vì sliding window của test trước có thể ảnh hưởng kết quả test sau.

## 13. Những lỗi thường gặp khi kiểm thử

| Biểu hiện | Nguyên nhân | Cách xử lý |
|---|---|---|
| Exception nghiệp vụ làm breaker OPEN | Chưa cấu hình ignore hoặc predicate quá rộng | Bổ sung ignore rule và test metric |
| Lỗi mới không làm failure rate tăng | Exception không nằm trong record list | Mở rộng danh sách hoặc dùng predicate |
| Ignore exception vẫn bị tính failure | Ignore predicate/class không khớp kiểu exception thực tế | Kiểm tra cause chain và exception được ném ra |
| Test OPEN không ổn định | Minimum calls, window hoặc threshold không phù hợp | Dùng cửa sổ nhỏ có kiểm soát và đủ mẫu xác định |
| Test thấy supplier chạy dù nghĩ breaker OPEN | Chưa đủ mẫu hoặc failure rate chưa chạm ngưỡng | Kiểm tra buffered calls và failure rate trước assertion |
| HTTP 503 bị tính success | Client trả response như giá trị bình thường | Ánh xạ thành exception hoặc dùng recordResult |
| Test dùng chung state | Tái sử dụng breaker giữa các test | Tạo instance riêng cho từng test |
| Predicate làm tăng latency | Có xử lý nặng hoặc I/O trong predicate | Chỉ thực hiện phép kiểm tra đồng bộ, nhẹ |

## Kết luận

`recordExceptions` xác định exception được tính là failure; khi dùng danh sách tường minh, exception không khớp thường được tính là success. `ignoreExceptions` loại exception khỏi cả success và failure, còn predicate cho phép phân loại theo điều kiện như HTTP status hoặc loại lỗi. Hãy kiểm thử cả exception truyền tới caller lẫn các metric buffered/success/failed, sau đó xác nhận failure rate làm breaker chuyển OPEN đúng ngưỡng. Cuối cùng, kiểm tra integration từ HTTP client tới Circuit Breaker để bảo đảm response lỗi thực sự được chuyển thành exception mà chính sách phân loại có thể nhận biết.

