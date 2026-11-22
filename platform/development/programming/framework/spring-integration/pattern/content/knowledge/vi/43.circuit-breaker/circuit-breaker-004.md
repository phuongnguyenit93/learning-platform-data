# Fallback khi circuit mở

## 1. Vấn đề: ngắt mạch thành công nhưng nghiệp vụ vẫn cần phản hồi

Trong một ứng dụng dùng **Spring Integration** để triển khai Enterprise Integration Patterns (EIP), một request có thể đi từ **Gateway** qua **Filter**, **Transformer**, **Router**, rồi tới **Service Activator** gọi API bên ngoài. Cách tổ chức này tách các bước xử lý bằng message channel và giúp flow dễ mở rộng. Tuy nhiên, khi dependency như dịch vụ tồn kho ngừng hoạt động, chỉ đặt circuit breaker để chặn lời gọi chưa đủ: phía nhận vẫn cần biết **request của mình sẽ được xử lý như thế nào**.

Circuit breaker có ba trạng thái cơ bản:

- **CLOSED:** cho gọi dependency và quan sát kết quả.
- **OPEN:** từ chối nhanh các lần gọi mới tới dependency.
- **HALF_OPEN:** cho một số lời gọi thăm dò theo chính sách của implementation; các request không được cấp quyền vẫn có thể bị từ chối.

**Fallback** là phương án xử lý được định nghĩa cho tình huống kết quả từ dependency không khả dụng. Fallback có thể trả kết quả cache được đánh dấu, thông báo lỗi rõ ràng, xử lý bằng dữ liệu thay thế đáng tin cậy hoặc đưa yêu cầu sang luồng chờ xử lý. Breaker **không tự tạo fallback**; luồng Spring Integration hoặc lớp ứng dụng phải quyết định rõ điều gì an toàn về mặt nghiệp vụ.

Bài này tập trung vào **fallback khi circuit OPEN**, đồng thời chỉ ra cách xử lý lỗi thực tế khi dependency thất bại trong CLOSED/HALF_OPEN, cách giữ correlation giữa các nhánh và cách kiểm thử để bảo đảm fallback không che mất tín hiệu lỗi mà breaker cần ghi nhận.

## 2. Fallback nằm ở đâu trong message flow?

~~~mermaid
flowchart TD
    A[Gateway nhận yêu cầu] --> B[Filter / Transformer]
    B --> C{Router}
    C -->|Cần tồn kho| D[Stock circuit breaker]
    C -->|Nhánh khác| S[Dependency độc lập]
    D -->|Được phép gọi| E[Stock API]
    D -->|Bị từ chối| F[Fallback policy]
    E -->|Thành công| G[Fresh stock result]
    E -->|Lỗi được ghi nhận| F
    F -->|Cache đủ điều kiện| H[STALE_REFERENCE]
    F -->|Không có dữ liệu an toàn| I[UNAVAILABLE / Fail fast]
    F -->|Công việc có thể hoãn| J[Queue / xử lý sau]
    G --> K[Gateway reply / Aggregator]
    H --> K
    I --> K
    S --> K
~~~

Sơ đồ thể hiện một **thiết kế lựa chọn theo yêu cầu nghiệp vụ**. Một request cụ thể thường áp dụng một trong các chính sách: trả dữ liệu cache, fail fast, hoặc hoãn công việc. Không mặc định vừa trả thành công vừa ghi một lệnh chưa rõ trạng thái vào queue.

**Thứ tự xử lý có ý nghĩa quyết định:**

1. Filter/Validator loại request không hợp lệ trước khi gọi dependency.
2. Circuit breaker bao quanh **thao tác thực sự gọi dependency**, để thấy được exception hoặc kết quả lỗi cần đo.
3. Chính sách fallback nằm **ngoài phần thực thi được bảo vệ** và nhận lỗi/tín hiệu từ chối sau khi breaker đã có cơ hội thống kê.
4. Gateway hoặc nhánh tiếp theo nhận một hợp đồng kết quả tường minh, ví dụ **FRESH**, **STALE_REFERENCE**, **UNAVAILABLE**.

Nếu đưa fallback vào **bên trong** lời gọi được circuit breaker bao quanh, một lỗi timeout có thể bị bắt rồi trả về object bình thường; breaker nhìn thấy một lần thành công và **không mở mạch dù API đang lỗi**. Đây là lỗi thiết kế phổ biến.

### Phân biệt hai nguồn kích hoạt fallback

| Tình huống | Điều đang xảy ra | Cần xử lý |
| --- | --- | --- |
| Breaker đã OPEN | Chưa gửi lời gọi mới tới dependency | Fallback ngay; không bắt buộc thử gọi lại |
| HALF_OPEN nhưng không còn permit | Lời gọi không được cấp quyền thăm dò | Cũng có thể fallback ngay |
| Breaker đang CLOSED, cuộc gọi bị timeout | Dependency đã được gọi và thất bại | Ghi nhận failure trước khi fallback |
| HALF_OPEN, lời gọi thăm dò thất bại | Dependency được gọi, có thể quay OPEN | Ghi nhận failure; fallback phù hợp |
| Lỗi validate dữ liệu đầu vào | Chưa nên gọi dependency | Trả validation error, **không** dùng cache giả |
| Lỗi lập trình tại Transformer | Không chứng minh dependency hỏng | Báo lỗi ứng dụng; không dùng fallback để giấu bug |

Với **Resilience4j**, lỗi **CallNotPermittedException** thể hiện lời gọi không được phép thực thi vì trạng thái breaker, thường là OPEN hoặc thiếu permit trong HALF_OPEN. Vì vậy tên reason code **BREAKER_REJECTED** chính xác hơn việc giả định mọi lần bị từ chối đều xảy ra khi OPEN.

## 3. Chọn fallback theo mức độ an toàn nghiệp vụ

Không phải dịch vụ nào cũng chấp nhận dữ liệu cũ hoặc hoàn thành tác vụ sau.

| Phương án | Phù hợp | Rủi ro cần kiểm soát |
| --- | --- | --- |
| **Fail fast** | Thanh toán, xác thực, chốt tồn kho, nghiệp vụ đòi hỏi dữ liệu mới | Trả lỗi phân biệt dependency không khả dụng với dữ liệu không hợp lệ |
| **Read-only cache** | Hiển thị danh mục, thông tin tham khảo, thống kê không tức thời | TTL, thời điểm tạo dữ liệu, khả năng thiếu dữ liệu, nhãn dữ liệu cũ |
| **Giảm chức năng** | Hiển thị trang sản phẩm nhưng ẩn nút mua khi chưa xác nhận tồn kho | Không trình bày dữ liệu giả là kết quả đáng tin cậy |
| **Queue / defer** | Gửi thông báo, đồng bộ dữ liệu, tạo báo cáo xử lý sau | Idempotency, durability, TTL, retry, dead-letter, giới hạn queue |
| **Nguồn thay thế** | Nhiều read replica hoặc provider dự phòng có hợp đồng tương thích | Nguồn thay thế cũng cần timeout, circuit riêng và kiểm soát độ nhất quán |

Ví dụ **API kiểm tra tồn kho** phục vụ hai nghiệp vụ:

- **Trang sản phẩm:** có thể hiển thị số lượng tham khảo từ cache và nhãn “cập nhật cách đây 1 phút”.
- **Bước xác nhận đặt hàng:** không được dựa vào số lượng cache để kết luận còn hàng; khi dependency đang OPEN, nên trả trạng thái **chưa xác nhận được** hoặc tạm dừng bước chốt đơn.

Cùng một nguồn dữ liệu nhưng **chính sách fallback có thể khác** theo use case. Vì thế nên thiết kế policy ở ranh giới nghiệp vụ thay vì dùng một giá trị mặc định kiểu **available = false** cho mọi nơi.

## 4. Thiết kế hợp đồng kết quả không gây hiểu nhầm

Một cách đơn giản là trả về một đối tượng có **trạng thái nguồn dữ liệu**, số liệu nếu có, thời điểm số liệu được lấy và correlation ID.

~~~java
public enum LookupStatus {
    FRESH,           // Kết quả mới từ dependency
    STALE_REFERENCE, // Kết quả cache chỉ dùng tham khảo
    UNAVAILABLE      // Không có dữ liệu đủ an toàn
}

public record InventoryRequest(
        String sku,
        int requestedQuantity,
        String correlationId
) {}

public record StockSnapshot(
        String sku,
        int availableUnits
) {}

public record CachedSnapshot(
        StockSnapshot snapshot,
        Instant capturedAt
) {}

public record InventoryReply(
        String sku,
        String correlationId,
        LookupStatus status,
        Integer availableUnits,
        Instant sourceTime,
        String reasonCode
) {}
~~~

Các quy ước nên thống nhất:

- **FRESH:** **availableUnits** có dữ liệu vừa nhận từ dependency; **sourceTime** phản ánh thời điểm lấy kết quả.
- **STALE_REFERENCE:** dữ liệu đến từ cache; **sourceTime** là thời điểm cache được tạo, không phải thời điểm xử lý request hiện tại. Có thể hiển thị để tham khảo nhưng không dùng thay cho bước xác nhận tồn kho.
- **UNAVAILABLE:** không có dữ liệu được chấp nhận; **availableUnits** và **sourceTime** có thể là **null**, thay vì gán số 0 khiến người dùng hiểu là hết hàng.
- **reasonCode:** giá trị máy đọc được như **BREAKER_REJECTED**, **UPSTREAM_FAILURE**, **CACHE_EXPIRED**, giúp UI, log và workflow quyết định cách phản hồi.
- **correlationId:** giữ nguyên định danh request để truy vết qua Gateway, Router, Splitter, Aggregator và error path.

Có thể bổ sung **dataVersion**, **cacheAge**, **retryable** hoặc **retryAfter** nếu hợp đồng thực sự cần. Tuy nhiên không nên biến mọi lỗi thành HTTP 200 thành công mà thiếu trạng thái suy giảm; status HTTP và trạng thái nghiệp vụ nên được ánh xạ có chủ đích ở boundary API.

## 5. Ví dụ Java: fallback nằm ngoài circuit breaker

Ví dụ sau dùng **Spring Integration Java DSL** để nối message flow và **Resilience4j** để bảo vệ thao tác gọi Stock API. Resilience4j được dùng vì lỗi từ chối khi OPEN/HALF_OPEN có exception tường minh và có thể định nghĩa sliding window. Với **RequestHandlerCircuitBreakerAdvice** native của Spring Integration, nguyên tắc đặt fallback **bên ngoài phần handler được advice bảo vệ** vẫn như nhau; cách nhận diện exception cụ thể phải theo API/phiên bản ứng dụng.

### 5.1. Dependency và cache chỉ đọc

Các interface định nghĩa một hợp đồng rõ ràng. Trong hệ thống thật, **StockClient** là HTTP/gRPC adapter có timeout và ánh xạ lỗi kết nối/5xx sang một exception riêng. Cache chỉ lưu các snapshot trước đó đã được xác minh.

~~~java
public interface StockClient {
    StockSnapshot fetch(String sku);
}

public interface InventoryCache {
    Optional<CachedSnapshot> find(String sku);
}

public class StockDependencyException extends RuntimeException {
    public StockDependencyException(String message, Throwable cause) {
        super(message, cause);
    }
}
~~~

Không nên catch chung mọi **RuntimeException** từ flow và xem là Stock API không khỏe. **StockDependencyException** là loại lỗi được adapter chuyển từ nguyên nhân của dependency, còn lỗi programming/validation phải được xử lý riêng.

### 5.2. Cấu hình breaker theo dependency

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
public class InventoryFlowConfig {

    @Bean
    public CircuitBreaker stockBreaker() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowSize(10)
                .minimumNumberOfCalls(5)
                .failureRateThreshold(50.0f)
                .waitDurationInOpenState(Duration.ofSeconds(15))
                .permittedNumberOfCallsInHalfOpenState(2)
                .build();

        return CircuitBreaker.of("stock-api", config);
    }

    @Bean
    public InventoryLookupService inventoryLookupService(
            CircuitBreaker stockBreaker,
            StockClient stockClient,
            InventoryCache inventoryCache
    ) {
        return new InventoryLookupService(
                stockBreaker,
                stockClient,
                inventoryCache,
                Clock.systemUTC(),
                Duration.ofMinutes(2)
        );
    }

    @Bean
    public IntegrationFlow inventoryFlow(
            InventoryLookupService lookupService
    ) {
        return IntegrationFlow.from("inventory.requests")
                .handle(
                        InventoryRequest.class,
                        (request, headers) -> lookupService.lookup(request)
                )
                .get();
    }
}

@MessagingGateway(defaultRequestChannel = "inventory.requests")
public interface InventoryGateway {
    InventoryReply lookup(InventoryRequest request);
}
~~~

Các import Java/Spring Integration/Resilience4j được lược bớt để giữ ví dụ dễ đọc. Trong ứng dụng Spring thực tế, cần khai báo dependency và đăng ký Gateway bằng **@IntegrationComponentScan** hoặc cấu hình tương đương.

### 5.3. Thực thi và xử lý fallback

~~~java
public class InventoryLookupService {

    private final CircuitBreaker breaker;
    private final StockClient stockClient;
    private final InventoryCache cache;
    private final Clock clock;
    private final Duration maxCacheAge;

    public InventoryLookupService(
            CircuitBreaker breaker,
            StockClient stockClient,
            InventoryCache cache,
            Clock clock,
            Duration maxCacheAge
    ) {
        this.breaker = breaker;
        this.stockClient = stockClient;
        this.cache = cache;
        this.clock = clock;
        this.maxCacheAge = maxCacheAge;
    }

    public InventoryReply lookup(InventoryRequest request) {
        // Chỉ thao tác gọi dependency nằm trong executeSupplier.
        try {
            StockSnapshot fresh = breaker.executeSupplier(
                    () -> stockClient.fetch(request.sku())
            );

            return new InventoryReply(
                    request.sku(),
                    request.correlationId(),
                    LookupStatus.FRESH,
                    fresh.availableUnits(),
                    clock.instant(),
                    "OK"
            );
        } catch (CallNotPermittedException rejected) {
            // OPEN hoặc HALF_OPEN không cấp permit.
            return fallback(request, "BREAKER_REJECTED");
        } catch (StockDependencyException dependencyError) {
            // Breaker đã nhìn thấy exception trước khi vào catch.
            return fallback(request, "UPSTREAM_FAILURE");
        }
    }

    private InventoryReply fallback(
            InventoryRequest request,
            String reason
    ) {
        Optional<CachedSnapshot> cached = cache.find(request.sku());
        Instant oldestAccepted = clock.instant().minus(maxCacheAge);

        if (cached.isPresent()
                && !cached.get().capturedAt().isBefore(oldestAccepted)) {
            CachedSnapshot entry = cached.get();

            return new InventoryReply(
                    request.sku(),
                    request.correlationId(),
                    LookupStatus.STALE_REFERENCE,
                    entry.snapshot().availableUnits(),
                    entry.capturedAt(),
                    reason
            );
        }

        return new InventoryReply(
                request.sku(),
                request.correlationId(),
                LookupStatus.UNAVAILABLE,
                null,
                null,
                "CACHE_MISSING_OR_EXPIRED"
        );
    }
}
~~~

**Vì sao cách đặt này bảo vệ được breaker?** Supplier bên trong **executeSupplier** chỉ gọi StockClient. Nếu StockClient ném **StockDependencyException**, breaker quan sát kết quả thất bại trước khi exception được bắt ở **InventoryLookupService.lookup** và chuyển thành fallback. Nếu mạch đã OPEN, supplier không chạy nên API bên ngoài không nhận thêm request.

Các điểm cần hoàn thiện trong ứng dụng thực tế:

1. **StockClient phải có timeout**. Breaker không tự hủy một HTTP call bị treo.
2. **Cache phải đáng tin cậy**. Nên kiểm tra cache lỗi hoặc không truy cập được rồi trả UNAVAILABLE/fail fast theo chính sách; một cache outage không nên khiến Gateway treo vô hạn.
3. **TTL phải theo nghiệp vụ**. Hai phút trong ví dụ chỉ là một giá trị minh họa; dữ liệu tồn kho biến động nhanh có thể không được dùng làm tham khảo lâu như vậy.
4. **Không dùng nhánh STALE_REFERENCE để chốt đơn**. Route đặt hàng phải yêu cầu xác nhận mới.
5. **Không nuốt lỗi lập trình**. Ví dụ chỉ bắt lỗi breaker từ chối và exception dependency có chủ đích.
6. **Ánh xạ trạng thái cho API caller**. UI có thể hiện thông báo, hoặc REST adapter chuyển UNAVAILABLE thành phản hồi lỗi có cấu trúc, tùy hợp đồng.

Trong ví dụ này, **InventoryCache** chỉ đọc. Việc làm mới cache cần một đường lưu riêng khi có dữ liệu fresh đã xác thực hoặc một quy trình đồng bộ độc lập, tránh cập nhật cache bằng dữ liệu fallback.

## 6. Native Spring Integration advice và vị trí fallback

Nếu flow dùng **RequestHandlerCircuitBreakerAdvice**, ý tưởng cốt lõi là **handler gọi dependency được advice bao quanh**, còn recovery/fallback xử lý ở một ranh giới **sau khi exception đã rời phần được bảo vệ**.

~~~mermaid
flowchart LR
    A[Gateway] --> B[Fallback boundary]
    B --> C[RequestHandlerCircuitBreakerAdvice]
    C --> D[Service Activator]
    D --> E[StockClient]
    C -->|Lỗi / từ chối| B
    B --> F[Outcome có status]
    E -->|Thành công| F
~~~

Cần phân biệt:

- Advice điều khiển việc có gọi Service Activator hay không, dựa trên lỗi được quan sát và trạng thái mạch.
- Thành phần fallback chuyển **lỗi từ advice/handler** thành outcome nghiệp vụ. Khi triển khai phải theo đúng exception, error channel và advice chain được cấu hình ở phiên bản Spring Integration đang dùng.
- Việc khai báo một error channel không tự động biến exception trong **Gateway đồng bộ qua DirectChannel** thành message rẽ nhánh. Nhiều trường hợp exception đi ngược về caller.
- Với endpoint chạy **poller** hoặc channel bất đồng bộ, lỗi có thể được bọc trong **ErrorMessage** gửi vào error channel phù hợp; handler ở error flow cần lấy được message gốc, cause và correlation ID.

Nếu bật cả **retry advice** và breaker, phải quyết định thứ tự rõ ràng. Đặt fallback trước khi breaker ghi nhận thất bại có thể khiến mạch không bao giờ mở; đặt retry không kiểm soát lên lỗi do mạch OPEN có thể tạo rất nhiều request nội bộ vô ích.

## 7. Fallback cache: xử lý TTL, nguồn dữ liệu và tính nhất quán

Cache hữu ích nhất cho **đọc dữ liệu phục vụ hiển thị**. Một fallback cache an toàn nên đáp ứng các điều kiện:

| Quy tắc | Cách thực hiện |
| --- | --- |
| Biết thời gian dữ liệu được lấy | Lưu **capturedAt** từ lúc có response fresh |
| Có giới hạn độ cũ | So sánh với TTL hoặc thời hạn theo use case |
| Không làm mất nguồn gốc | Trả **status = STALE_REFERENCE** và sourceTime |
| Không nhầm thiếu dữ liệu với số 0 | Trả **UNAVAILABLE** nếu không có snapshot |
| Chỉ lưu dữ liệu đã xác thực | Không cache dữ liệu lỗi/response chưa được kiểm chứng |
| Cache lỗi cũng có phương án | Timeout cache và fallback cuối cùng là UNAVAILABLE/fail fast |
| Không để cache lệch quyền truy cập | Key gồm các thuộc tính tenant/ngữ cảnh nếu dữ liệu không công khai |

**Ví dụ:** Snapshot tồn kho được lấy lúc 10:00:00, request đến lúc 10:01:00 và TTL hiển thị là 2 phút. Có thể trả **STALE_REFERENCE** với sourceTime 10:00:00. Request đến lúc 10:05:00 thì snapshot hết hạn, nên trả **UNAVAILABLE**; không nên gán **availableUnits = 0**.

Đối với dữ liệu phân quyền theo tenant, vùng, kho hay đơn vị tiền tệ, cache key phải bao gồm đầy đủ các chiều phân biệt. Cache chung theo SKU trong khi mỗi kho có tồn kho khác nhau là một lỗi nghiệp vụ nghiêm trọng.

## 8. Fallback bằng queue khi công việc có thể xử lý sau

Với những tác vụ không bắt buộc có kết quả tức thời, có thể thay vì gọi dependency đang OPEN, gửi message vào một hàng đợi bền vững để thực hiện sau:

~~~mermaid
flowchart TD
    A[Gateway / Command] --> B[Router / policy]
    B -->|Dependency sẵn sàng| C[Execute]
    B -->|Breaker từ chối| D[Persist outbox / durable queue]
    D --> E[ACK: ACCEPTED_FOR_LATER]
    D --> F[Consumer có retry backoff]
    F --> G{Dependency sẵn sàng?}
    G -->|Có| H[Thực thi idempotent]
    G -->|Chưa| I[Hoãn / DLQ theo giới hạn]
~~~

Chính sách này phù hợp cho **gửi email thông báo, xuất báo cáo hoặc đồng bộ hậu trường**. Nó không phù hợp với bước yêu cầu **quyết định ngay**, chẳng hạn trừ tiền hoặc xác nhận tồn kho mà ứng dụng lại trả kết quả hoàn thành trước khi công việc thật sự thành công.

Cần xác định:

- **ACK nghĩa là gì?** **ACCEPTED_FOR_LATER** chỉ khẳng định yêu cầu đã được lưu bền vững, chưa có nghĩa dependency đã xử lý thành công.
- **Không mất message:** chỉ trả ACK sau khi lưu vào queue/outbox thành công; xử lý transaction boundary phù hợp.
- **Idempotency key:** đề phòng consumer nhận lại cùng một message.
- **Retry có giới hạn:** backoff, jitter, số lần thử tối đa, dead-letter channel/queue và khả năng replay.
- **Hàng đợi có hạn mức:** timeout/TTL, queue depth, ngưỡng cảnh báo và chính sách khi queue đầy.
- **Giữ correlation:** bảo toàn request ID, tenant ID, trace/correlation ID để tìm lại tác vụ khi người dùng hỏi trạng thái.

Một breaker OPEN có thể khiến queue tích tụ rất nhanh. Nếu cứ “nhận để xử lý sau” vô hạn thì chỉ chuyển nghẽn từ HTTP client sang hàng đợi. Cần giám sát backpressure và giới hạn nhận việc.

## 9. Gateway, Router, Splitter, Aggregator và error channel

### 9.1. Gateway: caller phải thấy trạng thái suy giảm

Với Gateway đồng bộ, thiết kế hai hợp đồng rõ ràng:

- **Return outcome:** gọi phương thức Gateway trả **InventoryReply** có status **FRESH**, **STALE_REFERENCE**, **UNAVAILABLE**.
- **Fail fast bằng exception:** nếu nghiệp vụ không cho fallback, exception truyền về ứng dụng, và REST/controller boundary ánh xạ thành phản hồi dịch vụ tạm không khả dụng.

Không nên trả một **StockResult** giả giống hệt kết quả fresh chỉ để giữ nguyên chữ ký API. Caller không có cách phát hiện dữ liệu đã cũ, từ đó có thể đưa ra quyết định sai.

### 9.2. Router và Filter: chọn đường theo khả năng sử dụng kết quả

Router nên dựa trên **yêu cầu nghiệp vụ**: read-only display có thể đi vào nhánh cho phép cache; checkout buộc cần dữ liệu mới. Filter có thể từ chối request không hợp lệ trước khi chạm dependency. Có thể thêm Router phía sau fallback để đưa **UNAVAILABLE** vào luồng thông báo lỗi thay vì xử lý như một kết quả tồn kho hợp lệ.

### 9.3. Splitter và Aggregator: tránh chờ vô hạn

Giả sử Splitter tách đơn hàng thành ba message kiểm tra tồn kho từ các kho khác nhau. Một kho đang OPEN, hai kho còn lại trả dữ liệu fresh. Nếu nhánh OPEN bị loại bỏ mà không phát reply, Aggregator có thể chờ mãi.

Cách xử lý rõ ràng:

1. Gắn **correlation ID** theo đơn hàng và sequence metadata cho từng nhánh.
2. Nhánh bị OPEN trả một outcome **UNAVAILABLE/STALE_REFERENCE** phù hợp, giữ cùng correlation.
3. Aggregator nhận đủ ba outcome và quyết định **partial result**, thông báo thiếu dữ liệu hoặc từ chối xác nhận đơn.
4. Cấu hình group timeout, group expiration, discard/error path theo yêu cầu thực tế để tránh group tồn tại vô hạn khi có nhánh hoàn toàn mất tín hiệu.

Không trộn ý nghĩa **partial result** với **đã hoàn thành nghiệp vụ**. Trường hợp có nguy cơ sai dữ liệu, Aggregator nên báo chưa xác định thay vì tự giả định thành công.

### 9.4. Error channel và correlation

Khi một endpoint bất đồng bộ không xử lý được message, Spring Integration có thể dùng **ErrorMessage** chứa cause và thông tin message gốc. Error flow cần biết **dependency name**, **nguyên nhân**, **correlation ID**, **message ID**, chính sách retry và có thể thêm **idempotency key**.

Nếu ứng dụng quyết định trả outcome fallback ngay trong handler, có thể **không có exception nào được phát ra error channel**, vì lỗi đã được xử lý thành một kết quả. Khi đó phải chủ động ghi log/metrics cho tình trạng suy giảm; không dựa vào số ErrorMessage để đánh giá toàn bộ số lỗi.

## 10. Tránh retry, fallback và breaker tương tác sai

Ba cơ chế có vai trò khác nhau:

| Cơ chế | Chức năng | Nguyên tắc |
| --- | --- | --- |
| **Retry** | Thử lại lỗi tạm thời | Hữu hạn, backoff, chỉ dùng khi an toàn lặp |
| **Circuit breaker** | Ngăn tiếp tục gọi khi dependency không ổn | Quan sát đúng kết quả; chặn nhanh |
| **Fallback** | Định nghĩa kết quả khi không có dependency | Dữ liệu thay thế phải có trạng thái và điều kiện sử dụng |

Hai kiểu sắp xếp có thể cho kết quả khác nhau:

~~~mermaid
flowchart LR
    A[Gateway] --> B[Fallback]
    B --> C[Circuit breaker]
    C --> D[Retry hữu hạn]
    D --> E[Dependency]
~~~

Breaker bao ngoài retry có thể thấy **một kết quả cuối** cho request logic. Điều này có thể phù hợp khi muốn đánh giá request tổng thể. Nếu retry bao ngoài breaker, từng attempt có thể góp vào trạng thái mạch; sau khi OPEN, không retry mù quáng lỗi do breaker từ chối.

**Phản ví dụ:** bật retry 10 lần cho **CallNotPermittedException** rồi cuối cùng mới trả cache. Những attempt này không kiểm tra dependency phục hồi, chỉ tăng CPU, latency và log. Nên phân biệt lỗi **không được phép gọi** với lỗi mạng được phép retry.

**Phản ví dụ khác:** mỗi lần StockClient timeout, bắt exception trong supplier, trả object cache và báo thành công. Breaker thấy tất cả request “thành công” và không mở. Cách đúng là để breaker ghi nhận lỗi, rồi fallback bên ngoài chuyển thành outcome cho caller.

## 11. Kiểm thử fallback bằng fake dependency và call counter

Nên dùng **fake StockClient** điều khiển được kết quả, fake cache có dữ liệu mới/cũ, clock cố định và một breaker có ngưỡng thấp riêng cho test. Mục tiêu quan trọng nhất là chứng minh **khi OPEN, fallback vẫn trả theo hợp đồng và StockClient không bị gọi thêm**.

Ví dụ JUnit 5 minh họa, sử dụng các kiểu đã định nghĩa phía trên (import lược bớt):

~~~java
@Test
void openBreakerUsesCacheWithoutCallingStockAgain() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowSize(2)
            .minimumNumberOfCalls(2)
            .failureRateThreshold(100.0f)
            .waitDurationInOpenState(Duration.ofSeconds(30))
            .build();

    CircuitBreaker breaker = CircuitBreaker.of("stock-test", config);
    AtomicInteger remoteCalls = new AtomicInteger();

    StockClient failingClient = sku -> {
        remoteCalls.incrementAndGet();
        throw new StockDependencyException(
                "stock API timed out",
                new java.net.SocketTimeoutException()
        );
    };

    Clock clock = Clock.fixed(
            Instant.parse("2026-11-21T10:00:00Z"),
            ZoneOffset.UTC
    );

    InventoryCache cache = sku -> Optional.of(
            new CachedSnapshot(
                    new StockSnapshot(sku, 12),
                    Instant.parse("2026-11-21T09:59:00Z")
            )
    );

    InventoryLookupService service = new InventoryLookupService(
            breaker, failingClient, cache, clock, Duration.ofMinutes(2)
    );

    InventoryRequest request =
            new InventoryRequest("SKU-123", 2, "corr-1001");

    // Hai request đầu thực sự gọi dependency và nhận fallback.
    service.lookup(request);
    service.lookup(request);

    assertEquals(CircuitBreaker.State.OPEN, breaker.getState());
    assertEquals(2, remoteCalls.get());

    // Request thứ ba bị chặn ở breaker, dùng cache ngay.
    InventoryReply reply = service.lookup(request);
    assertEquals(2, remoteCalls.get());
    assertEquals(LookupStatus.STALE_REFERENCE, reply.status());
    assertEquals(Integer.valueOf(12), reply.availableUnits());
    assertEquals("BREAKER_REJECTED", reply.reasonCode());
    assertEquals("corr-1001", reply.correlationId());
}
~~~

**Ma trận kiểm thử cần bổ sung** cho flow thực tế:

| Kịch bản | Điều cần xác minh |
| --- | --- |
| CLOSED, Stock API trả thành công | **FRESH**, đúng dữ liệu; cache không được dùng làm kết quả chính |
| CLOSED, Stock API lỗi | Breaker ghi nhận lỗi; fallback trả outcome phù hợp |
| OPEN, cache còn trong TTL | **STALE_REFERENCE**, sourceTime chính xác, remote call counter không tăng |
| OPEN, cache hết TTL | **UNAVAILABLE**; không trả số lượng tồn kho giả |
| OPEN, cache lỗi hoặc không truy cập được | Có chính sách thoát an toàn; không treo Gateway |
| HALF_OPEN, không cấp permit | Có thể fallback; không tự coi đó là một probe đã thực hiện |
| HALF_OPEN, probe thành công | Phục hồi theo quy tắc breaker; request sau lại có thể FRESH |
| Lỗi validation ở Filter | Không vào StockClient, không dùng fallback để che lỗi |
| Retry kết hợp fallback | Giới hạn attempt, không retry lỗi breaker từ chối |
| Splitter/Aggregator có nhánh OPEN | Correlation vẫn đúng; group được giải phóng bằng outcome/timeout |
| Queue xử lý sau | Chỉ ACK sau khi lưu bền vững, replay an toàn nhờ idempotency |
| Có nhiều pod | Mỗi breaker có thể đang ở trạng thái khác nhau; kết quả fallback vẫn cùng hợp đồng |

Với các tình huống HALF_OPEN và thời gian chờ, dùng cấu hình test phù hợp hoặc clock mà thư viện hỗ trợ; không dựa vào sleep dài khiến test chậm và dễ không ổn định. Các ví dụ ở đây minh họa cách kiểm tra hành vi, không thay thế bài test tích hợp riêng cho phiên bản thư viện và transport thực tế.

## 12. Quan sát trạng thái suy giảm trong production

Một fallback có thể khiến user không nhìn thấy exception, nhưng hệ thống vẫn đang gặp sự cố. Vì vậy phải quan sát **breaker và fallback riêng biệt**:

| Metric hoặc log | Mục đích |
| --- | --- |
| Breaker state/transition theo dependency | Phân biệt CLOSED, OPEN, HALF_OPEN |
| Not-permitted calls | Đo số request bị chặn ngay ở breaker |
| Failure rate và client timeout | Biết dependency có đang thất bại thật không |
| **fallback_used** theo loại | Biết traffic nào đang dùng cache, fail fast hoặc defer |
| **cache_age** và cache miss | Theo dõi độ mới và độ tin cậy của fallback |
| Gateway latency / error rate | Đo tác động người dùng nhận thấy |
| Queue depth / oldest message age | Nhận biết tích tụ tác vụ chờ |
| Aggregator pending group / expired group | Phát hiện nhánh fallback hoặc error path làm mất kết quả |
| Correlation ID / trace ID | Điều tra một request qua các EIP |

Nên gắn tag **breaker name**, **dependency**, **fallback type**, **reason code** và **flow name** nhưng tránh đẩy SKU hoặc correlation ID có cardinality cao vào nhãn metric; các ID đó thích hợp hơn trong trace/log.

Cần cảnh báo nếu fallback cache bị sử dụng liên tục trong thời gian dài, cache age vượt giới hạn, queue tích tụ hoặc breaker chuyển **OPEN → HALF_OPEN → OPEN** lặp lại. Một hệ thống trả 200 cho mọi request nhờ fallback nhưng dựa trên dữ liệu quá cũ vẫn có thể vi phạm yêu cầu nghiệp vụ.

## 13. Các lỗi thường gặp khi thiết kế fallback

1. **Fallback nằm bên trong vùng breaker quan sát:** exception bị nuốt, mạch khó mở khi dependency lỗi thật.
2. **Trả dữ liệu cũ như thể fresh:** downstream dùng sai dữ liệu cho checkout/thanh toán.
3. **Gán số 0 khi cache miss:** không phân biệt “hết hàng” với “không biết”.
4. **Dùng cùng một fallback cho mọi use case:** trang tham khảo và bước xác nhận giao dịch có yêu cầu nhất quán khác nhau.
5. **Retry khi breaker OPEN:** làm tăng latency dù client không được gọi.
6. **Không đặt timeout cho client và cache:** fallback có thể bị chặn bởi chính nguồn dự phòng.
7. **Không giữ correlation khi rẽ nhánh:** Aggregator hoặc error flow không đối chiếu được message gốc.
8. **Queue vô hạn hoặc ACK trước khi lưu bền vững:** gây mất tác vụ hoặc tích tụ ngoài kiểm soát.
9. **Chỉ đo lỗi upstream:** fallback trả kết quả nên lỗi thực tế giảm trên biểu đồ, che khuất tình trạng suy giảm kéo dài.
10. **Không phân biệt lỗi lập trình với lỗi dependency:** fallback che bug nội bộ, làm việc tìm nguyên nhân khó hơn.

## 14. Checklist áp dụng cho Spring Integration

- [ ] Breaker đặt sát lời gọi dependency; fallback nằm sau ranh giới breaker để lỗi được ghi nhận.
- [ ] Chọn fail fast, cache, nguồn dự phòng hoặc queue theo yêu cầu nhất quán của nghiệp vụ.
- [ ] Outcome phân biệt rõ **FRESH**, **STALE_REFERENCE**, **UNAVAILABLE** và có correlation ID.
- [ ] Cache có TTL, source timestamp, cache key đúng ngữ cảnh và chính sách khi cache miss.
- [ ] Client thực có timeout; retry hữu hạn, không retry lỗi bị breaker từ chối.
- [ ] Gateway trả phản hồi suy giảm có cấu trúc; không che lỗi validation bằng fallback.
- [ ] Flow bất đồng bộ xác định đúng error channel; Splitter/Aggregator có phương án cho nhánh thiếu kết quả.
- [ ] Nếu dùng queue, có persistence, idempotency, giới hạn backpressure và dead-letter.
- [ ] Test OPEN bằng **remote call counter**, cache miss/expired, HALF_OPEN và đường correlation.
- [ ] Quan sát **fallback rate**, cache age, breaker rejected calls và ảnh hưởng lên Gateway/queue.

**Fallback khi circuit mở** biến một cơ chế ngắt lời gọi thành chính sách suy giảm dịch vụ có chủ đích. Trong Spring Integration, một fallback đúng giúp Gateway trả kết quả rõ ràng, Router và Aggregator xử lý được nhánh không khả dụng, đồng thời cho breaker ghi nhận đủ thất bại của dependency và ngăn hệ thống tiếp tục bị kéo chậm bởi sự cố bên ngoài.
