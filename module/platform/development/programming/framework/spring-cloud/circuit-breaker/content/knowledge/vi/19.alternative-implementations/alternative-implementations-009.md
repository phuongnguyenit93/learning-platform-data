# Kiểm thử hợp đồng và giới hạn khi đổi nhà cung cấp

Trong Spring Cloud CircuitBreaker, ứng dụng sử dụng một API chung để tạo và gọi Circuit Breaker mà không phải gọi trực tiếp API của từng thư viện. Nhờ lớp trừu tượng này, ứng dụng có thể thay implementation, chẳng hạn giữa các tích hợp được hỗ trợ trong release train đang dùng, với ít thay đổi hơn ở mã gọi. Tuy nhiên, API chung không bảo đảm mọi implementation có cùng hành vi, cấu hình, metric hay khả năng bảo vệ.

Khi đổi nhà cung cấp Circuit Breaker, cần kiểm thử hai loại hợp đồng: hợp đồng giữa ứng dụng và dịch vụ phụ thuộc, cùng hợp đồng hành vi mà ứng dụng mong đợi từ Circuit Breaker. Kiểm thử giúp phát hiện khác biệt về exception, fallback, trạng thái, timeout, giới hạn đồng thời, reactive pipeline và quan sát vận hành trước khi triển khai implementation mới.

## 1. Phân biệt hợp đồng dịch vụ và hợp đồng Circuit Breaker

Có hai lớp hợp đồng cần được giữ ổn định:

| Hợp đồng | Nội dung cần bảo đảm | Ví dụ |
|---|---|---|
| Hợp đồng HTTP/API của dependency | Đường dẫn, phương thức HTTP, request/response schema, mã trạng thái và ý nghĩa nghiệp vụ | **GET /products/{id}** trả Product hoặc lỗi 404 |
| Hợp đồng bảo vệ của ứng dụng | Khi dependency chậm hoặc lỗi, ứng dụng phản hồi ra sao và Circuit Breaker kiểm soát lời gọi thế nào | Timeout chuyển sang fallback; OPEN từ chối lời gọi mới |

Contract test của dịch vụ Catalog có thể xác nhận response JSON, trường bắt buộc và ý nghĩa của HTTP 404/503. Những kiểm thử này giúp ứng dụng phát hiện khi nhà cung cấp dịch vụ thay đổi API.

Contract test của Circuit Breaker lại tập trung vào hành vi phía ứng dụng: lời gọi thành công trả kết quả bình thường; lỗi được phân loại đúng; fallback nhận đúng nguyên nhân; trạng thái OPEN ngăn gọi dependency; HALF_OPEN chỉ cho phép số probe theo chính sách; và ứng dụng vẫn xuất metric cần thiết.

Hai loại hợp đồng bổ trợ nhau. Một HTTP API giữ nguyên schema nhưng đổi cách trả mã 503 thành 200 với payload lỗi vẫn có thể làm thay đổi cách Circuit Breaker ghi nhận kết quả. Ngược lại, provider Circuit Breaker thay đổi nhưng HTTP contract của Catalog vẫn giữ nguyên. Vì vậy, cần kiểm tra cả hai lớp.

## 2. Lớp trừu tượng Spring Cloud CircuitBreaker che giấu điều gì?

Mã ứng dụng có thể sử dụng factory chung để tạo Circuit Breaker theo tên:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
class CatalogGateway {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final CatalogClient catalogClient;
    private final ProductCache productCache;

    CatalogGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            CatalogClient catalogClient,
            ProductCache productCache) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.catalogClient = catalogClient;
        this.productCache = productCache;
    }

    Product getProduct(String id) {
        return circuitBreakerFactory.create("catalog").run(
            () -> catalogClient.getProduct(id),
            error -> productCache.findById(id)
                .orElseThrow(() ->
                    new CatalogUnavailableException(id, error)
                )
        );
    }
}
~~~

Service sử dụng **CircuitBreakerFactory** và không cần biết trực tiếp registry hay builder riêng của Resilience4j. Đây là phần được abstraction chuẩn hóa: tạo Circuit Breaker theo ID và thực thi lời gọi với hành vi dự phòng.

Tuy nhiên, factory không làm cho mọi chi tiết của implementation trở nên giống nhau. Các khác biệt có thể còn lại gồm:

- Cách cấu hình failure rate, slow-call rate, cửa sổ trượt và thời gian OPEN.
- Cách nhận diện exception được ghi nhận, bỏ qua hoặc chuyển thành kết quả thành công.
- Cách timeout và cancellation tác động lên Future hoặc reactive subscription.
- Kiểu Bulkhead, giới hạn đồng thời và cách từ chối khi hết tài nguyên.
- Cách Retry tương tác với Circuit Breaker và thứ tự decorator.
- Tên metric, tag, event, trạng thái được xuất ra và API quản trị.
- Khả năng hỗ trợ blocking, reactive, annotation và fallback theo từng kiểu trả về.

Khi đổi provider, cần xem abstraction là ranh giới API của mã gọi. Không nên xem nó là lời hứa rằng cấu hình hoặc semantics của provider cũ có thể chuyển nguyên xi sang provider mới.

## 3. Xác định hợp đồng hành vi trước khi đổi provider

Trước khi thay implementation, hãy mô tả hành vi mà ứng dụng cần giữ. Một hợp đồng tối thiểu có thể gồm:

1. Lời gọi thành công phải trả đúng dữ liệu và không kích hoạt fallback.
2. Lỗi kỹ thuật được xác định là lỗi dependency phải được ghi nhận theo chính sách.
3. Lỗi nghiệp vụ như ProductNotFound không được làm tăng failure rate nếu không phản ánh sức khỏe dịch vụ.
4. Khi Circuit Breaker OPEN, lời gọi mới bị từ chối trước khi client gọi dependency.
5. Fallback trả đúng kiểu kết quả và giữ đúng ý nghĩa nghiệp vụ.
6. Sau thời gian chờ, HALF_OPEN chỉ cấp số probe đã cấu hình.
7. Nếu probe thành công đủ điều kiện, bộ ngắt trở lại CLOSED; nếu thất bại, bộ ngắt mở lại.
8. Timeout và giới hạn đồng thời không vượt ngân sách tài nguyên của ứng dụng.
9. Metric và log vẫn đủ để phân biệt lỗi dependency, timeout, lời gọi bị từ chối và fallback.

Những điều này tạo thành tiêu chí chấp nhận độc lập với tên thư viện. Khi provider mới không đáp ứng một yêu cầu, nhóm cần quyết định điều chỉnh cấu hình, bổ sung cơ chế khác hoặc không thực hiện chuyển đổi.

## 4. Kiểm thử hợp đồng HTTP của dependency

Contract test ở biên HTTP xác nhận ứng dụng và dependency hiểu cùng một giao thức. Có thể dùng Spring Cloud Contract, Pact hoặc một HTTP stub trong kiểm thử tích hợp. Công cụ cụ thể phụ thuộc cách nhóm quản lý hợp đồng giữa consumer và provider.

Ví dụ, ứng dụng mong đợi Catalog trả về Product khi tìm thấy:

~~~json
{
  "id": "SKU-001",
  "name": "Mechanical Keyboard",
  "available": true
}
~~~

Contract cần xác định rõ:

- Request dùng HTTP method và path nào.
- Trường nào bắt buộc trong response.
- Kiểu dữ liệu của từng trường.
- Mã HTTP khi tìm thấy, không tìm thấy, request không hợp lệ hoặc dịch vụ tạm thời không sẵn sàng.
- Cấu trúc lỗi và trường mã lỗi ổn định.
- Header hoặc correlation ID cần truyền qua các dịch vụ.

Không nên chỉ kiểm tra response có status 200. Nếu Catalog trả status 200 cho một payload biểu diễn lỗi kỹ thuật, Circuit Breaker có thể xem lời gọi là thành công trừ khi ứng dụng kiểm tra payload và chuyển nó thành exception. Contract phải thể hiện rõ semantics của response, không chỉ cấu trúc JSON.

Contract test cũng nên kiểm tra timeout ở tầng HTTP client và việc truyền cancellation nếu client hỗ trợ. Circuit Breaker provider không thể bù cho một HTTP client không có giới hạn thời gian chờ hoặc không giải phóng tài nguyên khi request bị hủy.

## 5. Kiểm thử hợp đồng của lớp gateway trong ứng dụng

Có thể kiểm thử lớp gateway ở mức service bằng cách thay client bằng stub hoặc mock. Mục tiêu là xác nhận ứng dụng truyền đúng tham số, phân loại lỗi và trả fallback đúng ý nghĩa.

Ví dụ kiểm thử các trường hợp của **CatalogGateway**:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

import org.junit.jupiter.api.Test;

class CatalogGatewayTest {

    @Test
    void returnsCatalogProductWhenDependencySucceeds() {
        // Arrange: client trả về sản phẩm hợp lệ.
        // Act: gọi gateway.getProduct("SKU-001").
        // Assert: trả về Product từ Catalog và không dùng cache fallback.
    }

    @Test
    void usesCacheWhenDependencyFails() {
        // Arrange: client phát lỗi kỹ thuật và cache có sản phẩm.
        // Act: gọi gateway.getProduct("SKU-001").
        // Assert: trả về sản phẩm từ cache.
    }

    @Test
    void reportsUnavailableWhenDependencyAndCacheFail() {
        // Arrange: client lỗi và cache không có dữ liệu.
        // Act: gọi gateway.getProduct("SKU-001").
        // Assert: ném CatalogUnavailableException với nguyên nhân phù hợp.
    }
}
~~~

Đây là unit test cho logic ứng dụng. Nếu factory cũng được mock, test không chứng minh provider thực tế chuyển trạng thái hoặc áp dụng cấu hình. Muốn kiểm tra những hành vi đó, cần integration test khởi tạo đúng starter và implementation đang sử dụng.

Không nên để toàn bộ kiểm thử chỉ mock **CircuitBreakerFactory**. Mock giúp kiểm tra cách service sử dụng abstraction, nhưng không phát hiện lỗi do auto-configuration, tên instance sai, cấu hình properties không được bind hoặc semantics của provider khác với mong đợi.

## 6. Xây dựng bộ contract test cho Circuit Breaker

Một bộ kiểm thử provider nên dùng cùng một tập tiêu chí hành vi. Có thể tổ chức thành các test case độc lập:

| Test case | Điều kiện | Kết quả cần xác nhận |
|---|---|---|
| Thành công | Dependency trả dữ liệu hợp lệ | Trả kết quả bình thường; fallback không chạy |
| Lỗi kỹ thuật | Dependency phát exception được ghi nhận | Failure được tính theo exception policy |
| Lỗi nghiệp vụ | Dependency trả exception được bỏ qua | Không retry và không làm tăng failure rate nếu chính sách quy định bỏ qua |
| OPEN | Đã tạo đủ mẫu lỗi để mở mạch | Lời gọi mới bị từ chối; client không được gọi thêm |
| HALF_OPEN | Hết thời gian OPEN | Chỉ số probe được cấu hình được phép thực thi |
| Phục hồi | Probe thành công | Bộ ngắt trở về CLOSED theo chính sách |
| Tiếp tục lỗi | Probe thất bại | Bộ ngắt quay lại OPEN |
| Fallback lỗi | Nguồn dự phòng cũng thất bại | Caller nhận lỗi fallback rõ ràng; không mất nguyên nhân |
| Timeout | Dependency vượt thời hạn | Caller nhận timeout hoặc fallback theo hợp đồng |
| Hết Bulkhead | Đạt giới hạn đồng thời | Lời gọi bị từ chối đúng loại và tài nguyên được giải phóng |

Khi kiểm thử trạng thái, dùng thời gian cấu hình ngắn trong test profile và đồng hồ hoặc cơ chế chờ có giới hạn. Tránh dùng **Thread.sleep** dài tùy tiện vì làm test chậm và dễ chập chờn. Với provider có hỗ trợ clock tùy chỉnh, có thể dùng clock giả để kiểm soát thời gian. Nếu không, dùng polling có timeout rõ ràng để chờ trạng thái mong muốn.

Mỗi test nên làm rõ đang kiểm tra hợp đồng chung hay đặc tính riêng của provider. Ví dụ, tên event hoặc metric cụ thể có thể khác nhau giữa implementation; test chung chỉ nên xác nhận tín hiệu nghiệp vụ cần thiết, còn tên metric và event chi tiết thuộc test adapter/provider.

## 7. Kiểm tra exception policy và fallback khi đổi provider

Một khác biệt quan trọng là cách provider ghi nhận exception. Ứng dụng cần giữ được phân loại giữa:

- Lỗi kỹ thuật như connect failure, HTTP 5xx hoặc timeout.
- Lỗi nghiệp vụ như sản phẩm không tồn tại hoặc không đủ hàng.
- Lỗi bị Circuit Breaker từ chối như **CallNotPermittedException**.
- Lỗi nội bộ như mapper hoặc code ứng dụng phát sinh exception.

Ví dụ, nếu **ProductNotFoundException** trước đây được bỏ qua trong failure rate nhưng provider mới ghi nhận nó là lỗi, Circuit Breaker có thể mở khi người dùng tìm nhiều mã không tồn tại. Ngược lại, nếu HTTP 503 bị xem là kết quả thành công, bộ ngắt sẽ không bảo vệ dependency khi dịch vụ quá tải.

Cần kiểm tra fallback ở các trường hợp:

1. Fallback được gọi khi lỗi kỹ thuật xảy ra.
2. Fallback được gọi khi Circuit Breaker từ chối lời gọi.
3. Fallback nhận đúng exception hoặc nguyên nhân mà ứng dụng cần phân loại.
4. Fallback trả đúng kiểu đồng bộ hoặc reactive.
5. Lỗi của fallback được truyền ra ngoài theo hợp đồng.
6. Fallback không gọi lại chính dependency đang gặp sự cố.

Nếu ứng dụng dùng annotation **@CircuitBreaker** với **fallbackMethod**, cần kiểm tra riêng chữ ký fallback, quy tắc chọn overload và Spring AOP proxy. Không thể giả định provider mới hỗ trợ annotation hoặc resolver fallback giống hệt provider cũ. Với API functional của Spring Cloud CircuitBreaker, kiểm thử cách truyền supplier và fallback function trực tiếp.

## 8. Kiểm thử blocking và reactive riêng biệt

Một provider có thể hỗ trợ API blocking nhưng có giới hạn hoặc cách cấu hình khác đối với reactive. Vì vậy, không dùng kết quả test blocking để kết luận reactive hoạt động tương đương.

Với blocking, kiểm tra:

- Supplier chỉ được thực thi khi Circuit Breaker cho phép.
- Timeout không giữ thread hoặc connection quá thời hạn thiết kế.
- Cancellation có tác động như dự kiến với Future và client.
- Fallback trả kiểu đồng bộ phù hợp.

Với reactive, kiểm tra:

- Publisher nguồn không bị subscribe sớm ngoài ý muốn.
- Lỗi đồng bộ khi tạo Publisher được chuyển thành tín hiệu reactive nếu cần.
- **onError** đi qua Circuit Breaker trước khi fallback phục hồi.
- Cancellation của subscription được truyền đến client ở mức hỗ trợ.
- Không có lời gọi **block()** trên event loop.
- Fallback trả Mono hoặc Flux đúng kiểu và chỉ thực thi theo subscription.

Ví dụ reactive dùng factory chung:

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import reactor.core.publisher.Mono;

class ReactiveCatalogGateway {

    private final ReactiveCircuitBreakerFactory<?, ?> factory;
    private final ReactiveCatalogClient client;
    private final ProductCache cache;

    ReactiveCatalogGateway(
            ReactiveCircuitBreakerFactory<?, ?> factory,
            ReactiveCatalogClient client,
            ProductCache cache) {
        this.factory = factory;
        this.client = client;
        this.cache = cache;
    }

    Mono<Product> getProduct(String id) {
        return factory.create("catalog").run(
            Mono.defer(() -> client.getProduct(id)),
            error -> cache.findByIdReactive(id)
                .switchIfEmpty(Mono.error(
                    new CatalogUnavailableException(id, error)
                ))
        );
    }
}
~~~

Kiểm thử phải subscribe vào Mono để kích hoạt lời gọi và xác nhận tín hiệu. Chỉ tạo Publisher mà không subscribe chưa kiểm tra được request hoặc Circuit Breaker đã thực thi. Nếu dùng Reactor Test, có thể dùng **StepVerifier** để xác nhận giá trị, lỗi và việc hoàn tất.

## 9. Cấu hình của provider không chuyển đổi một-một

Các implementation có thể dùng thuật ngữ, cấu trúc và khả năng khác nhau. Ví dụ, cấu hình Resilience4j có thể gồm **slidingWindowType**, **minimumNumberOfCalls**, **failureRateThreshold**, **slowCallRateThreshold**, **waitDurationInOpenState** và **permittedNumberOfCallsInHalfOpenState**. Provider khác có thể không có thuộc tính cùng tên hoặc dùng thuật toán khác.

Không nên chỉ đổi tên prefix YAML rồi cho rằng chính sách đã được chuyển đổi. Cần lập bảng ánh xạ:

| Yêu cầu nghiệp vụ | Cấu hình provider cũ | Cách biểu diễn ở provider mới |
|---|---|---|
| Đủ số mẫu trước khi đánh giá | **minimumNumberOfCalls** | Xác minh provider có khái niệm tương đương |
| Cửa sổ theo số lượng hoặc thời gian | **slidingWindowType**, **slidingWindowSize** | Kiểm tra thuật toán và đơn vị cửa sổ |
| Ngưỡng lỗi | **failureRateThreshold** | Xác minh cách tính và thời điểm mở |
| Ngưỡng lời gọi chậm | **slowCallRateThreshold**, **slowCallDurationThreshold** | Có thể cần metric hoặc timeout riêng nếu provider không hỗ trợ |
| Thời gian OPEN | **waitDurationInOpenState** | Xác minh thời gian chờ và chuyển sang trạng thái thử lại |
| Số probe HALF_OPEN | **permittedNumberOfCallsInHalfOpenState** | Xác minh giới hạn và cách xử lý probe đồng thời |
| Timeout | TimeLimiter | Có thể cần cấu hình ở HTTP client hoặc một cơ chế riêng |
| Bulkhead | Semaphore hoặc thread-pool bulkhead | Xác minh loại cô lập và giới hạn hàng đợi |

Nếu provider mới không có tính năng tương đương, hãy ghi rõ khoảng trống. Có thể giữ TimeLimiter hoặc Bulkhead ở một lớp độc lập nếu kiến trúc cho phép, nhưng cần kiểm thử thứ tự phối hợp và semantics của exception. Không nên âm thầm bỏ một cơ chế đang là yêu cầu vận hành.

## 10. Giới hạn khi đổi nhà cung cấp

Lớp trừu tượng làm giảm phụ thuộc trực tiếp vào thư viện, nhưng không loại bỏ các ràng buộc sau:

**Khác biệt về state machine.** Provider có thể khác cách tính mẫu, điều kiện chuyển OPEN, thời điểm HALF_OPEN và xử lý probe đang chạy. Cùng một ngưỡng số học không bảo đảm thời điểm mở mạch giống nhau.

**Khác biệt về exception.** Tên lớp exception, wrapping và cách bỏ qua lỗi có thể thay đổi. Fallback hoặc Retry dựa trên một exception cụ thể có thể cần điều chỉnh.

**Khác biệt về fallback.** Functional fallback trong **run** và annotation fallbackMethod có thể có hỗ trợ, chữ ký hoặc resolver khác nhau. Fallback theo overload không nên được xem là hợp đồng chung nếu provider không bảo đảm.

**Khác biệt về timeout và cancellation.** Một provider có thể tích hợp TimeLimiter với Future, provider khác dựa vào HTTP client hoặc reactive operator. Timeout của caller không bảo đảm server đã dừng xử lý.

**Khác biệt về Bulkhead và Retry.** Provider có thể hỗ trợ giới hạn đồng thời, retry hoặc decorator theo cách khác. Thứ tự phối hợp ảnh hưởng số lần dependency được gọi và số mẫu Circuit Breaker ghi nhận.

**Khác biệt về reactive.** Không phải implementation nào cũng cung cấp cùng mức hỗ trợ cho Mono/Flux, cancellation và backpressure. Cần xác minh đúng starter và factory reactive của release train.

**Khác biệt về metric và event.** Tên metric, tag, event publisher và API truy vấn trạng thái có thể thay đổi. Dashboard và alert có thể cần cập nhật ngay cả khi hành vi nghiệp vụ được giữ nguyên.

**Khác biệt về auto-configuration.** Starter, dependency management, property prefix và điều kiện tạo bean có thể khác. Việc ứng dụng khởi động thành công chưa chứng minh provider đã được kích hoạt hoặc cấu hình đã được bind.

## 11. Quy trình đổi provider có kiểm soát

Có thể thực hiện chuyển đổi theo các bước:

1. **Ghi lại baseline:** lưu cấu hình, trạng thái, tỷ lệ lỗi, timeout, fallback rate, số lời gọi và độ trễ của provider hiện tại.
2. **Xác định contract:** viết rõ hành vi thành công, lỗi kỹ thuật, lỗi nghiệp vụ, OPEN, HALF_OPEN, timeout, Bulkhead và fallback.
3. **Kiểm tra khả năng provider mới:** xác minh release train, starter, blocking/reactive support và các tính năng cần dùng.
4. **Ánh xạ cấu hình:** chuyển chính sách theo ý nghĩa, không sao chép máy móc tên thuộc tính.
5. **Chạy contract test:** dùng cùng bộ test cho provider cũ và mới; so sánh kết quả, exception, số lần gọi và trạng thái.
6. **Kiểm thử tích hợp:** xác nhận auto-configuration, properties, service discovery, fallback và metrics trong ứng dụng thực.
7. **Triển khai có kiểm soát:** dùng môi trường thử nghiệm hoặc một nhóm instance giới hạn trước khi mở rộng.
8. **So sánh vận hành:** theo dõi tỷ lệ lỗi, timeout, số lời gọi bị từ chối, fallback, tài nguyên và độ trễ.
9. **Giữ khả năng quay lại:** lưu artifact và cấu hình provider cũ để rollback nếu contract hoặc SLO không đạt.

Không nên đổi provider đồng thời với việc thay API dependency, timeout, retry policy và fallback. Nếu nhiều biến cùng thay đổi, khó xác định nguyên nhân khi kết quả khác baseline. Thay đổi từng lớp và giữ bộ contract test ổn định sẽ giúp khoanh vùng vấn đề.

## 12. Ma trận kiểm thử trước khi chấp nhận provider mới

Bảng dưới đây có thể dùng làm checklist review. Các giá trị cụ thể cần được điều chỉnh theo SLA và lưu lượng của dịch vụ.

| Nhóm | Kiểm thử bắt buộc | Tiêu chí chấp nhận |
|---|---|---|
| API contract | Schema, status, error code, timeout HTTP | Consumer và provider hiểu cùng semantics |
| Normal path | Dependency thành công | Kết quả và độ trễ trong giới hạn |
| Failure classification | 4xx nghiệp vụ, 5xx kỹ thuật, connect error | Được record/ignore đúng chính sách |
| Circuit state | CLOSED → OPEN → HALF_OPEN → CLOSED/OPEN | Chuyển trạng thái theo hợp đồng |
| Rejection | Gọi khi OPEN hoặc hết probe | Dependency không nhận lời gọi bị từ chối |
| Fallback | Cache có dữ liệu, cache rỗng, cache lỗi | Response đúng nghĩa; lỗi fallback không bị che |
| TimeLimiter | Dependency chậm hơn timeout | Caller nhận timeout/fallback đúng hạn |
| Cancellation | Future hoặc subscription bị hủy | Tài nguyên được giải phóng ở mức client hỗ trợ |
| Bulkhead | Vượt giới hạn đồng thời | Từ chối có kiểm soát, không làm cạn tài nguyên |
| Reactive | Subscribe, onError, cancellation | Pipeline đúng, không block event loop |
| Observability | Metric, tag, event, log và alert | Dashboard phân biệt đúng nguyên nhân |
| Compatibility | Starter, BOM, auto-configuration | Chỉ một implementation mong muốn được kích hoạt |

Ngoài kết quả PASS/FAIL, nên lưu lại số liệu đo được của mỗi provider: số request đến dependency, số lần retry, tỷ lệ fallback, thời gian mở mạch, số probe và p95/p99. Những số liệu này giúp nhận ra khác biệt về hành vi mà một test đơn lẻ có thể không phát hiện.

## 13. Tình huống thực hành

Một ứng dụng Spring Boot đang dùng Resilience4j thông qua Spring Cloud CircuitBreaker để bảo vệ Catalog. Nhóm muốn thử một implementation khác được hỗ trợ trong release train hiện tại.

Trước khi chuyển đổi, nhóm ghi nhận hợp đồng:

- ID Circuit Breaker là **catalog** và ổn định theo dependency.
- HTTP 503, connect failure và timeout được phân loại là lỗi kỹ thuật.
- HTTP 404 theo hợp đồng là lỗi nghiệp vụ, không làm tăng failure rate.
- Khi OPEN, client Catalog không được gọi thêm.
- Sau thời gian chờ, chỉ hai probe được phép chạy trong HALF_OPEN.
- Fallback dùng cache và trả Product hoặc CatalogUnavailableException.
- API reactive phải trả Mono và không block event loop.
- Dashboard phải phân biệt timeout, lỗi dependency và lời gọi bị từ chối.

Nhóm sau đó:

1. Giữ nguyên service sử dụng **CircuitBreakerFactory** và **ReactiveCircuitBreakerFactory**.
2. Thay starter implementation theo hướng dẫn phiên bản Spring Cloud đang dùng.
3. Ánh xạ các yêu cầu trên sang cấu hình của provider mới; đánh dấu những tính năng không có tương đương trực tiếp.
4. Chạy cùng bộ test với mock dependency và test HTTP contract.
5. Khởi động ứng dụng bằng profile tích hợp để xác minh factory được inject và instance **catalog** nhận cấu hình.
6. Tạo chuỗi lỗi để kiểm tra OPEN, gọi thử khi OPEN để xác nhận không phát sinh HTTP request, rồi kiểm tra HALF_OPEN và phục hồi.
7. So sánh metric, fallback, timeout và độ trễ với baseline của Resilience4j.

Nếu provider mới không hỗ trợ giới hạn probe cần thiết hoặc không phân biệt được lỗi nghiệp vụ với lỗi kỹ thuật theo yêu cầu, nhóm chưa thể coi việc chuyển đổi là tương đương. Cần bổ sung cơ chế riêng, thay đổi hợp đồng có phê duyệt hoặc giữ implementation cũ cho đến khi khoảng trống được giải quyết.

## Kết luận

Spring Cloud CircuitBreaker giúp giảm phụ thuộc vào API riêng của một thư viện, nhưng không làm cho các provider có semantics giống nhau. Trước khi đổi implementation, hãy kiểm thử hợp đồng HTTP của dependency và hợp đồng hành vi của Circuit Breaker; xác minh exception, fallback, state machine, timeout, Bulkhead, reactive support và observability. Chỉ chấp nhận provider mới khi cùng bộ contract test đạt yêu cầu và các khác biệt cấu hình hoặc tính năng đã được đánh giá rõ ràng.
