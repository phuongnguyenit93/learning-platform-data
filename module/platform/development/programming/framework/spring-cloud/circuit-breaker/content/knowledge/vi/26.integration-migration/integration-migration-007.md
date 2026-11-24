# Kiểm thử hồi quy số liệu, luồng xử lý và ngữ nghĩa fallback

Khi chuyển backend của Spring Cloud Circuit Breaker, nâng phiên bản Spring Cloud/Resilience4j hoặc thay đổi cách cấu hình, ứng dụng có thể vẫn biên dịch và khởi động nhưng hành vi bảo vệ đã khác trước. Một ngưỡng lỗi thay đổi, exception bị phân loại khác, fallback chạy ở thời điểm khác hoặc retry bị lồng thêm có thể làm thay đổi response mà caller nhận được và tải gửi tới dependency.

Kiểm thử hồi quy cần so sánh **hợp đồng quan sát được** của ứng dụng trước và sau chuyển đổi: dữ liệu trả về, exception, số lần gọi dependency, trạng thái breaker, số liệu lỗi/chậm, fallback và thời gian xử lý. Không nên chỉ kiểm tra rằng bean `CircuitBreakerFactory` được tạo hoặc endpoint trả HTTP 200.

Trong module Spring Cloud Circuit Breaker, backend có thể là Resilience4j hoặc một implementation khác như Spring Retry. Mỗi backend có mô hình thống kê, API sự kiện và metric riêng. Vì vậy, bài kiểm thử nên tách hai lớp: kiểm tra hành vi nghiệp vụ mà mọi backend phải giữ nguyên, sau đó kiểm tra các đặc tính riêng của backend mới.

## Xác định baseline trước khi chuyển đổi

Trước khi thay dependency hoặc cấu hình, lưu lại một baseline từ phiên bản đang chạy. Baseline cần gắn với cùng tập dữ liệu, tải, lỗi giả lập và thời hạn request để có thể so sánh công bằng.

| Nhóm | Baseline cần ghi nhận |
|---|---|
| Response | HTTP status, schema, trường dữ liệu, header và ý nghĩa kết quả suy giảm |
| Dependency call | Số lần gọi, số lần retry, timeout, lỗi kết nối và request bị từ chối |
| Circuit breaker | ID instance, trạng thái, thời điểm chuyển trạng thái, ngưỡng và cửa sổ |
| Fallback | Điều kiện kích hoạt, số lần chạy, kết quả trả về và lỗi phát sinh trong fallback |
| Latency | p50, p95, p99, thời gian chờ dependency và thời gian request đầu cuối |
| Tài nguyên | In-flight calls, connection pool, thread, Bulkhead rejection và cancellation |
| Telemetry | Metric, tag, event, log và trace có thể dùng để chẩn đoán |

Ghi rõ version Spring Boot, Spring Cloud release train, backend circuit breaker và Resilience4j/Spring Retry. Khi chuyển đổi, giữ nguyên tải và kịch bản lỗi để khác biệt quan sát được chủ yếu đến từ integration mới. Nếu đồng thời thay timeout, retry và threshold, sẽ khó xác định nguyên nhân của thay đổi.

## Xây dựng ma trận hồi quy hành vi

Mỗi dependency được bảo vệ nên có một ma trận tối thiểu. Ma trận này mô tả input, điều kiện lỗi và hành vi cần giữ nguyên:

| Kịch bản | Hành vi cần xác minh |
|---|---|
| Dependency thành công nhanh | Caller nhận đúng dữ liệu; fallback không chạy; một lần gọi nghiệp vụ tạo đúng số request dự kiến |
| Dependency trả lỗi được ghi nhận | Breaker ghi nhận lỗi; caller nhận fallback hoặc exception theo hợp đồng |
| Exception bị bỏ qua | Không làm tăng failure rate nếu exception được cấu hình ignore |
| Dependency phản hồi chậm | Slow-call rate tăng theo ngưỡng; response vẫn có thể thành công |
| Request vượt timeout | Caller kết thúc trong deadline; timeout được phân loại đúng và không giữ tài nguyên vô hạn |
| Breaker `OPEN` | Supplier không được gọi; lời gọi bị từ chối; fallback hoặc lỗi từ chối đúng hợp đồng |
| Breaker `HALF_OPEN` | Số probe không vượt quota; kết quả tốt/xấu đưa breaker về trạng thái đúng |
| Fallback cũng lỗi | Exception từ fallback được truyền theo hợp đồng; không che giấu lỗi thứ hai |
| Retry được kích hoạt | Số attempt, backoff và tổng thời gian nằm trong giới hạn đã định |
| Request bị hủy | Cancellation truyền tới publisher/client và tài nguyên được giải phóng |

Ma trận cần kiểm tra cả kết quả bên ngoài lẫn số lần dependency được gọi. Một response fallback đúng nội dung nhưng dependency bị gọi ba lần ngoài ý muốn vẫn là hồi quy về tải và có thể gây lỗi dây chuyền.

## Kiểm tra cấu hình và ngữ nghĩa sliding window

Khi chuyển backend hoặc version, các thuộc tính cùng tên có thể có semantics khác nhau, hoặc backend mới không hỗ trợ một số thuộc tính của backend cũ. Kiểm tra rõ:

- `slidingWindowType`, `slidingWindowSize` và `minimumNumberOfCalls`.
- `failureRateThreshold` và `slowCallRateThreshold`.
- `slowCallDurationThreshold`.
- `waitDurationInOpenState`, `permittedNumberOfCallsInHalfOpenState` và `maxWaitDurationInHalfOpenState`.
- `recordExceptions`, `ignoreExceptions` và các predicate phân loại lỗi.
- Cách bật auto transition, TimeLimiter, Bulkhead và metric.

Với Resilience4j, failure rate và slow-call rate được tính riêng trên cùng mẫu số. Một lời gọi vừa lỗi vừa chậm đóng góp vào cả hai nhóm chuyên biệt nhưng chỉ tăng tổng số lời gọi một lần. Breaker mở khi một trong hai tỷ lệ đạt ngưỡng sau khi có đủ số mẫu. Hãy tạo test biên cho tỷ lệ bằng đúng threshold, vì điều kiện “đạt ngưỡng” bao gồm trường hợp bằng ngưỡng.

Nếu backend cũ chỉ có retry policy hoặc circuit breaker theo thời gian mở/reset, không thể so sánh trực tiếp số liệu đó với sliding window của Resilience4j. Hãy ghi rõ khác biệt semantics và xác định tiêu chí tương đương ở cấp ứng dụng, ví dụ thời gian tối đa tiếp tục gửi request sau khi dependency lỗi.

Ví dụ test state machine Resilience4j với cửa sổ nhỏ, xác định:

```java
CircuitBreakerConfig config = CircuitBreakerConfig.custom()
        .slidingWindowType(CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
        .slidingWindowSize(4)
        .minimumNumberOfCalls(4)
        .failureRateThreshold(50)
        .waitDurationInOpenState(Duration.ofSeconds(30))
        .permittedNumberOfCallsInHalfOpenState(2)
        .build();

CircuitBreaker breaker = CircuitBreaker.of("catalog-test", config);

for (int i = 0; i < 2; i++) {
    assertThrows(IllegalStateException.class,
            () -> breaker.executeSupplier(() -> {
                throw new IllegalStateException("dependency failed");
            }));
}
for (int i = 0; i < 2; i++) {
    assertEquals("ok", breaker.executeSupplier(() -> "ok"));
}

assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
assertEquals(50.0f, breaker.getMetrics().getFailureRate(), 0.01f);
assertThrows(CallNotPermittedException.class,
        () -> breaker.executeSupplier(() -> "must not run"));

breaker.transitionToHalfOpenState();
assertEquals("probe-1", breaker.executeSupplier(() -> "probe-1"));
assertEquals("probe-2", breaker.executeSupplier(() -> "probe-2"));
assertEquals(CircuitBreaker.State.CLOSED, breaker.getState());
```

Test dùng chuyển trạng thái tường minh để kiểm tra cách breaker đánh giá probe; nó không thay thế integration test cho việc tự chuyển `OPEN` sang `HALF_OPEN` sau thời gian thực. Với kiểm thử timer, dùng clock/scheduler test được backend hỗ trợ thay vì dựa vào sleep dài.

## Kiểm tra exception classification

Một thay đổi nhỏ trong loại exception mà HTTP client phát ra có thể làm failure rate biến động lớn. Ví dụ, backend cũ có thể nhận `ResourceAccessException`, trong khi client mới phát `WebClientRequestException` hoặc `TimeoutException`. Nếu cấu hình `recordExceptions` không cập nhật, breaker mới có thể xem lỗi kết nối là thành công hoặc bỏ qua ngoài ý muốn.

Tạo test riêng cho từng nhóm exception:

| Loại kết quả | Kiểm tra |
|---|---|
| Exception cần ghi nhận | Failure counter tăng và failure rate được cập nhật |
| Exception được ignore | Không tăng failure counter; xác minh không bị tính nhầm thành thành công |
| Exception nghiệp vụ hợp lệ | Không mở breaker nếu hợp đồng coi đây là kết quả bình thường |
| Timeout của client | Được phân loại đúng theo chính sách; thời gian hoàn tất không vượt deadline |
| `CallNotPermittedException` | Không gọi dependency; xác minh fallback xử lý theo chính sách |
| `BulkheadFullException` | Phân biệt từ chối do concurrency cục bộ với lỗi của dependency từ xa |

Không chỉ assert loại exception cuối cùng mà caller nhận được. Fallback có thể biến exception gốc thành DTO; hãy quan sát exception trước fallback hoặc metric/event của breaker để chắc rằng lỗi gốc được ghi nhận đúng.

## Hồi quy ngữ nghĩa fallback

Fallback là một phần của hợp đồng ứng dụng. Khi thay backend, kiểm tra cả điều kiện kích hoạt lẫn kết quả:

1. Fallback chạy khi supplier thất bại theo chính sách đã định.
2. Fallback chạy khi breaker từ chối lời gọi ở `OPEN`, nếu thiết kế yêu cầu.
3. Fallback không chạy khi dependency trả thành công.
4. Fallback không biến lỗi validation hoặc authorization thành dữ liệu giả hợp lệ.
5. Fallback trả đúng schema, status code, nguồn dữ liệu và độ mới đã công bố.
6. Fallback chỉ chạy đúng số lần dự kiến và không gọi lại dependency đang lỗi.
7. Nếu fallback ném exception, caller nhận lỗi đó theo hợp đồng và telemetry vẫn giữ được nguyên nhân ban đầu.

Ví dụ kiểm tra fallback với API `CircuitBreaker` của Spring Cloud:

```java
AtomicInteger dependencyCalls = new AtomicInteger();
AtomicInteger fallbackCalls = new AtomicInteger();

String result = circuitBreaker.run(
        () -> {
            dependencyCalls.incrementAndGet();
            throw new IOException("catalog unavailable");
        },
        error -> {
            fallbackCalls.incrementAndGet();
            return "cached-result";
        }
);

assertEquals("cached-result", result);
assertEquals(1, dependencyCalls.get());
assertEquals(1, fallbackCalls.get());
```

Đây là test ở cấp API đồng bộ của Spring Cloud Circuit Breaker. Với reactive, fallback phải trả `Mono`/`Flux` cùng kiểu phần tử và cần dùng `StepVerifier` để xác minh subscription, tín hiệu và cancellation. Đừng coi fallback phát `onNext` rồi `onComplete` là bằng chứng dependency đã thành công; breaker vẫn phải ghi nhận kết quả của nguồn được bảo vệ.

### Phân biệt fallback theo nguyên nhân

Nếu fallback xử lý nhiều nguyên nhân, hãy kiểm tra từng nguyên nhân độc lập. `CallNotPermittedException` nghĩa là breaker không cấp quyền gọi; timeout nghĩa là request đã được thực thi nhưng không hoàn tất trong thời hạn; lỗi kết nối có thể xảy ra trước khi server nhận request. Các tình huống này có thể cần response khác nhau, đặc biệt với thao tác có side effect và kết quả chưa xác định.

Không retry một thao tác ghi với idempotency key mới chỉ vì timeout. Khi không biết dependency đã xử lý hay chưa, giữ nguyên key và truy vấn trạng thái hoặc gửi lại cùng key theo hợp đồng downstream.

## Kiểm tra thứ tự Retry, CircuitBreaker và TimeLimiter

Khi thay đổi cách bọc, thứ tự decorator có thể làm thay đổi số lần breaker ghi nhận:

- `Retry(CircuitBreaker(call))`: mỗi attempt đi qua breaker; breaker có thể quan sát từng lần thất bại.
- `CircuitBreaker(Retry(call))`: breaker quan sát kết quả cuối cùng của cả chuỗi retry.

Kiểm tra số lần gọi thật, tổng thời gian và số lỗi được ghi nhận. Ví dụ, nếu retry tối đa ba attempt, test cần chứng minh dependency không bị gọi quá ba lần và tổng thời gian không vượt deadline của caller. Nếu breaker đang `OPEN`, không retry liên tục `CallNotPermittedException`; đây là quyết định từ chối có chủ đích.

TimeLimiter và timeout của HTTP client cũng cần được kiểm tra riêng. Timeout từng attempt phải phù hợp với deadline tổng thể; ba lần retry với timeout bốn giây có thể làm caller chờ lâu hơn nhiều so với SLO nếu không có deadline ngoài. Timeout ở một tầng không bảo đảm request từ xa đã dừng, do đó kiểm tra cancellation và tài nguyên in-flight.

## Chuẩn hóa metric để so sánh backend

Tên metric, tag và cách xuất event có thể thay đổi giữa backend hoặc version. Không nên viết test hồi quy gắn cứng vào toàn bộ tên metric nội bộ nếu ứng dụng không coi đó là API công khai. Thay vào đó, xây một mô hình quan sát chuẩn ở cấp ứng dụng:

```java
public record BreakerObservation(
        String dependency,
        String state,
        long successfulCalls,
        long failedCalls,
        long slowCalls,
        long notPermittedCalls,
        Double failureRate,
        Double slowCallRate
) {}
```

Adapter telemetry của mỗi backend ánh xạ metric mà nó thực sự hỗ trợ vào mô hình này. Nếu backend cũ không có slow-call metric, biểu diễn trường đó là không hỗ trợ/không có dữ liệu thay vì giả định giá trị `0`. `0` có nghĩa đã đo và không có lời gọi chậm; `null` hoặc trạng thái unsupported có nghĩa backend không cung cấp phép đo.

Khi so sánh trước và sau migration, dùng cùng định nghĩa về:

- Lời gọi thành công, lỗi, chậm và bị từ chối.
- Tỷ lệ trên mẫu số nào và trong khoảng thời gian nào.
- ID dependency và replica.
- Thời điểm phát event và cách đếm retry attempt.
- Cardinality của tag và cách tổng hợp giữa các pod.

Metric nội bộ của Resilience4j có thể được xuất qua Micrometer khi có dependency phù hợp. Kiểm tra metric tại ranh giới scrape/registry của ứng dụng và xác minh tag `name`/dependency có giá trị ổn định. Không đưa request ID, user ID hoặc tham số URL vào metric label.

## Kiểm thử reactive và cancellation

Với `ReactiveCircuitBreaker`, dùng `StepVerifier` để kiểm tra các tín hiệu mà caller quan sát:

```java
when(catalogClient.findProduct("p-1"))
        .thenReturn(Mono.error(new IOException("catalog offline")));

StepVerifier.create(catalogService.findProduct("p-1"))
        .assertNext(product -> {
            assertEquals("p-1", product.id());
            assertFalse(product.isAvailable());
        })
        .verifyComplete();

verify(catalogClient, times(1)).findProduct("p-1");
```

Kiểm tra thêm:

- Publisher nguồn chỉ được subscribe khi caller subscribe.
- Fallback được subscribe khi nguồn lỗi hoặc breaker từ chối.
- `Mono`/`Flux` không phát thêm tín hiệu sau `onError` hoặc `onComplete`.
- Cancellation truyền tới client và giải phóng Bulkhead permit/resource.
- Retry không tạo subscription ngoài dự kiến.
- Timeout nằm trong ranh giới mà circuit breaker cần ghi nhận.

`StepVerifier.withVirtualTime` có thể điều khiển scheduler Reactor cho delay, retry backoff và `timeout(Duration)`. Nó không tự điều khiển clock nội bộ của mọi backend circuit breaker hoặc HTTP client. Dùng cơ chế clock/scheduler test của đúng thư viện khi kiểm tra state transition theo thời gian.

## Kiểm thử tích hợp Spring context

Unit test với mock hữu ích để xác minh logic fallback và số lần gọi, nhưng không chứng minh auto-configuration hoặc factory wiring hoạt động đúng. Bổ sung integration test khởi động Spring context với backend đích và xác minh:

1. Đúng starter/backend được nạp.
2. Factory nhận đúng ID và instance cấu hình.
3. Properties/Customizer có hiệu lực như dự kiến.
4. AOP proxy hoạt động nếu dùng annotation Resilience4j.
5. Metric/event được phát sau khi gọi thật qua bean Spring.
6. WebFlux và blocking path dùng đúng factory tương ứng.
7. Không có hai wrapper circuit breaker ngoài ý muốn quanh cùng một thao tác.

Gọi service từ bean được inject trong context. Nếu tự khởi tạo bằng `new`, test sẽ bỏ qua Spring proxy và có thể không kiểm tra được annotation/AOP. Nếu dùng factory, kiểm tra ID thực tế và bảo đảm registry/instance không bị tạo lại theo từng request.

## So sánh dưới tải và triển khai canary

Sau khi test chức năng qua, chạy cùng một profile tải trên phiên bản cũ và mới. So sánh throughput, p95/p99 latency, tỷ lệ lỗi, số lần fallback, số request bị từ chối, concurrency và tài nguyên. Đặc biệt kiểm tra khi dependency suy giảm: backend mới có ngắt request đủ sớm không, có tạo nhiều retry hơn không và có để request treo sau khi breaker đổi trạng thái không.

Triển khai theo từng bước:

1. Chạy test hồi quy và contract test trong CI.
2. Chạy integration test với dependency giả lập có thể trả thành công, lỗi, chậm và không phản hồi.
3. Chạy load test và fault injection với cùng dữ liệu giữa hai phiên bản.
4. Đưa backend mới lên một nhóm canary hoặc một phần traffic.
5. So sánh metric đã chuẩn hóa và response thực tế với baseline.
6. Mở rộng khi SLO, fallback và tải dependency đều trong giới hạn; rollback nếu phát hiện sai lệch có ảnh hưởng người dùng.

Không dùng một trạng thái breaker duy nhất ở một replica để kết luận toàn cluster. Mỗi JVM thường có state machine local; quan sát theo replica và tổng hợp với cùng semantics.

## Tiêu chí chấp nhận migration

Một lần chuyển đổi chỉ nên được xem là đạt khi:

- Response và hợp đồng nghiệp vụ không thay đổi ngoài những khác biệt đã được phê duyệt.
- Exception được phân loại đúng; lỗi cần ghi nhận không bị bỏ qua và lỗi nghiệp vụ không mở breaker ngoài ý muốn.
- Số attempt, retry, timeout và tổng thời gian nằm trong deadline.
- `CLOSED`, `OPEN`, `HALF_OPEN` cùng quota probe hoạt động theo chính sách đã định.
- Fallback chạy đúng điều kiện, đúng số lần và trả đúng schema/ngữ nghĩa.
- Metric/event có thể quan sát và được ánh xạ nhất quán; khác biệt không thể ánh xạ được ghi rõ.
- Cancellation giải phóng tài nguyên; không có request treo sau timeout hoặc state transition.
- Load test và canary không làm SLO xấu đi hoặc tăng tải bất thường lên dependency.

## Checklist hồi quy cuối cùng

1. Lưu version, cấu hình và baseline trước migration.
2. Liệt kê từng dependency, ID breaker và failure domain.
3. Kiểm tra success, error, ignored exception, slow call và timeout.
4. Kiểm tra cửa sổ, minimum calls, threshold, OPEN duration và HALF_OPEN quota.
5. Kiểm tra fallback cho lỗi dependency, breaker open, lỗi nghiệp vụ và fallback failure.
6. Kiểm tra số attempt và thứ tự Retry/CircuitBreaker/TimeLimiter.
7. Kiểm tra reactive subscription, signal, cancellation và backpressure nếu có.
8. Chuẩn hóa metric và event; không nhầm metric không hỗ trợ với giá trị bằng không.
9. Chạy integration test qua Spring context và factory thật.
10. Chạy fault/load test, canary và so sánh với baseline trước khi mở rộng.

Kiểm thử hồi quy tốt chứng minh rằng integration mới vẫn bảo vệ đúng dependency và vẫn giữ hợp đồng với caller. Hãy so sánh hành vi, số liệu và luồng xử lý bằng các kịch bản xác định; chỉ chấp nhận khác biệt có chủ đích, có giải thích và có thể quan sát trong vận hành.
