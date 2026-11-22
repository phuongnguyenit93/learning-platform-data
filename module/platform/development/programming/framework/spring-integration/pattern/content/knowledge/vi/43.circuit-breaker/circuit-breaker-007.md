# Circuit breaker theo endpoint hoặc tenant

## 1. Vì sao phạm vi của circuit breaker quan trọng?

Trong **SPRING_INTEGRATION_PATTERN**, một hệ thống có thể nhận message qua Gateway, lọc bằng Filter, chuyển đổi qua Transformer, chọn nhánh bằng Router rồi gọi các dịch vụ ngoài qua Service Activator. Các channel của Spring Integration giúp xây dựng luồng theo Enterprise Integration Patterns (EIP) với mức phụ thuộc thấp, nhưng sự cố tại một dependency vẫn có thể lan sang những message khác nếu giới hạn bảo vệ không đúng.

Giả sử hệ thống thương mại điện tử có hai API:

- **Stock API** để tra tồn kho.
- **Pricing API** để lấy giá.

Nếu cả hai dùng **chung một circuit breaker**, khi Stock API liên tục timeout, breaker OPEN có thể từ chối cả request lấy giá dù Pricing API vẫn khỏe. Một ví dụ khác: một provider đa tenant áp dụng quota riêng cho từng tenant. Tenant A bị trả HTTP 429 liên tục nhưng tenant B vẫn được phục vụ. Nếu dùng một breaker chung cho mọi tenant, lỗi của A có thể khiến B bị chặn theo.

**Circuit breaker theo endpoint hoặc tenant** là cách chọn phạm vi bộ ngắt mạch phù hợp với **miền lỗi** (*failure domain*): những lời gọi có chung nguyên nhân hỏng hoặc chung chính sách giới hạn thường cần được đánh giá cùng nhau; những nhóm có thể hỏng độc lập có thể cần trạng thái breaker độc lập.

Việc phân vùng phải có giới hạn. Tạo một breaker cho mọi URL, SKU, user ID hoặc request ID khiến số instance tăng vô hạn, mỗi breaker có ít dữ liệu thống kê và hệ thống khó vận hành. Mục tiêu là **cô lập lỗi đúng chỗ với số lượng breaker có thể kiểm soát được**.

## 2. Breaker scope: một khóa cho một miền lỗi

Mỗi instance breaker có trạng thái **CLOSED / OPEN / HALF_OPEN** và lịch sử thống kê riêng. Ta chọn một **breaker key** ổn định để xác định lời gọi nào dùng chung instance.

~~~mermaid
flowchart TD
    A[Gateway] --> B[Filter / Transformer]
    B --> C{Router theo nghiệp vụ}
    C -->|Tra tồn kho| D[Breaker: stock.read]
    C -->|Đặt giữ tồn kho| E[Breaker: stock.reserve]
    C -->|Tra giá| F[Breaker: pricing.read]
    D --> G[Stock read endpoint]
    E --> H[Stock reserve endpoint]
    F --> I[Pricing endpoint]
~~~

Ví dụ ba breaker trên có thể độc lập nếu các operation được triển khai và thất bại độc lập. Ngược lại, nếu cả ba endpoint đều đi qua **cùng một cluster phụ thuộc đã ngừng hoạt động**, việc chia breaker theo operation không loại bỏ được lỗi chung; mỗi breaker vẫn có thể đưa thêm traffic tới cluster trước khi mở.

### 2.1. Các cách chọn key phổ biến

| Phạm vi | Key minh họa | Khi nên dùng | Hạn chế |
| --- | --- | --- | --- |
| Theo service | **stock-service** | Nhiều lời gọi cùng một miền lỗi | Một endpoint lỗi có thể tác động endpoint khỏe |
| Theo operation / endpoint logic | **stock.read**, **stock.reserve** | Read/write có chính sách hoặc hạ tầng độc lập | Quá nhiều endpoint nhỏ sẽ phân tán số mẫu |
| Theo vùng triển khai | **stock.read:ap-southeast**, **stock.read:eu-west** | Mỗi vùng có backend và khả năng lỗi riêng | Dùng sai nếu traffic cùng đi tới một upstream |
| Theo tenant | **stock.read:tenant-A** | Tenant có quota, instance hoặc kết nối riêng | Cardinality lớn, tenant ít traffic dễ thiếu mẫu |
| Theo nhóm tenant | **stock.read:shared**, **stock.read:enterprise-A** | Cần bảo vệ riêng vài tenant lớn, còn lại dùng chung | Các tenant trong nhóm shared vẫn ảnh hưởng lẫn nhau |

**Endpoint ở đây là một operation ổn định**, không phải URL nguyên văn chứa tham số. Ví dụ các URL **/stock/SKU-1** và **/stock/SKU-2** cùng là operation **stock.read**. Nếu lấy cả SKU làm breaker key, mỗi mặt hàng có trạng thái riêng và breaker khó tích lũy đủ lỗi để nhận ra API tồn kho đang ngừng hoạt động.

Tương tự, không nên dùng request ID, correlation ID, đường dẫn có query parameters hay chuỗi tenant chưa xác thực làm key.

### 2.2. Đặt câu hỏi về miền lỗi trước khi chia breaker

1. Hai lời gọi có dùng **cùng upstream instance, connection pool hoặc quota** không?
2. Một endpoint/tenant bị lỗi có thể xảy ra **mà các nhóm còn lại vẫn khỏe** không?
3. Có đủ số request ở mỗi nhóm để kết luận breaker nên OPEN không?
4. Có yêu cầu **cách ly SLA, hợp đồng hoặc bảo mật** giữa các tenant không?
5. Số lượng key có ổn định và đủ nhỏ để theo dõi, kiểm thử, dọn dẹp không?

Phạm vi thực tế đôi khi là tổ hợp **service + operation + region + tenant group**, nhưng không nên thêm tất cả các chiều nếu không có bằng chứng chúng đại diện cho miền lỗi độc lập.

## 3. Cô lập theo endpoint: thiết kế trực quan nhất

Một ứng dụng có thể gọi hai endpoint trên cùng backend, nhưng cách sử dụng và yêu cầu lỗi khác nhau.

| Điểm gọi | Vai trò nghiệp vụ | Chính sách ví dụ |
| --- | --- | --- |
| **stock.read** | Đọc tồn kho phục vụ hiển thị | Có thể fallback cache tham khảo |
| **stock.reserve** | Giữ hàng cho đơn đặt | Thường cần dữ liệu xác nhận mới, fail fast khi lỗi |
| **pricing.read** | Tra giá | Có thể có timeout và SLO riêng |
| **shipping.quote** | Tính phí vận chuyển | Có thể thử provider dự phòng nếu được phép |

Một breaker riêng cho **stock.reserve** tránh việc read traffic thất thường trực tiếp làm khóa operation giữ hàng, miễn là miền lỗi đủ độc lập. Nhưng nếu cả hai operation cùng phụ thuộc vào một database đang mất kết nối, hai breaker vẫn có thể mở; cần quan sát cả sức khỏe hệ thống chung.

Trong Spring Integration, Router chuyển message đến đúng channel; từng Service Activator dùng một advice/breaker riêng:

~~~mermaid
flowchart LR
    A[Order Gateway] --> B[Validate]
    B --> C{Router}
    C -->|read| D[Channel stock.read]
    C -->|reserve| E[Channel stock.reserve]
    D --> F[Breaker read]
    E --> G[Breaker reserve]
    F --> H[Stock read client]
    G --> I[Stock reserve client]
~~~

**Gắn breaker sát thao tác gọi dependency**. Filter không nên làm mở mạch vì quantity âm; lỗi parse của Transformer không nên tính vào trạng thái stock API. Nếu cùng một endpoint được gọi bởi nhiều flow, nên dùng cùng một instance breaker cho endpoint đó khi chúng chia sẻ miền lỗi và chính sách.

## 4. Cô lập theo tenant: khi nào thực sự cần?

Ở một dịch vụ đa tenant, mỗi request mang ngữ cảnh tenant được xác thực. Nếu provider áp dụng **quota riêng**, **hệ thống dữ liệu riêng**, **kết nối riêng** hoặc **SLA riêng**, một tenant có thể thất bại độc lập với tenant khác.

~~~mermaid
flowchart TD
    A[Gateway + authenticated tenant context] --> B[Resolve bounded breaker scope]
    B --> C{Scope}
    C -->|Tenant A có circuit riêng| D[stock.read:DEDICATED_A]
    C -->|Tenant B có circuit riêng| E[stock.read:DEDICATED_B]
    C -->|Các tenant thông thường| F[stock.read:SHARED]
    D --> G[Stock client, tenant A]
    E --> H[Stock client, tenant B]
    F --> I[Stock client, tenant từ request đã xác thực]
~~~

Trong ví dụ này, tenant A lỗi đến mức mạch của A OPEN thì tenant B vẫn có thể gọi qua breaker của B. Các tenant trong nhóm SHARED cùng chia sẻ thống kê: nếu một tenant làm lỗi liên tục, nhóm shared cũng có thể bị ảnh hưởng. Đây là lựa chọn có chủ đích khi số lượng tenant lớn hoặc lưu lượng của từng tenant thấp.

### Khi nào nên dùng breaker theo từng tenant?

- Upstream có **rate limit/quota riêng theo tenant**, ví dụ tenant A hết quota trong khi B vẫn có quota.
- Mỗi tenant đi đến **database schema/cluster/provider** hoặc credential riêng, nên lỗi có thể độc lập.
- Một số tenant có **SLA cao** và cần giới hạn sự ảnh hưởng từ traffic của tenant khác.
- Có đủ số mẫu/traffic để trạng thái breaker theo từng tenant phản ánh lỗi thực, thay vì liên tục thiếu minimum calls.

### Khi nào không nên?

- Mọi tenant đều gọi **cùng một endpoint chung** và phần lớn sự cố là lỗi toàn bộ upstream. Tách quá nhỏ khiến hàng nghìn breaker đều phải tự “học” rằng backend đã hỏng.
- Có hàng chục nghìn tenant với lưu lượng rất thấp; mỗi breaker giữ thống kê rời rạc, không phát hiện sự cố kịp thời.
- Key tenant được lấy trực tiếp từ input không đáng tin cậy. Một client có thể tạo vô số key để tăng số breaker hoặc cố tình làm lệch trạng thái.

**Không nhầm breaker với quota enforcement.** Breaker phát hiện tình trạng lời gọi lỗi/chậm; quota/rate limiter chủ động hạn chế số request, còn bulkhead giới hạn tài nguyên đồng thời. Với đa tenant, thường cần cả **breaker + per-tenant rate limit/bulkhead** tùy yêu cầu công bằng tài nguyên.

## 5. Ma trận chọn phạm vi

| Tình huống | Phạm vi nên cân nhắc | Lý do |
| --- | --- | --- |
| Stock và Pricing là hai hệ thống độc lập | Mỗi dependency một breaker | Stock hỏng không tự khóa Pricing |
| Stock read và reserve chạy trên cluster độc lập | Theo operation/endpoint | Có thể lỗi độc lập |
| Stock read/reserve cùng cluster thường hỏng chung | Theo service hoặc có bảo vệ cấp service | Tránh nhiều breaker cùng bắn traffic vào nơi hỏng |
| Tenant A/B có quota/provider độc lập | Theo tenant hoặc nhóm tenant riêng | Lỗi A không làm chặn B |
| Nhiều tenant nhỏ cùng một endpoint | Shared breaker | Đủ mẫu và số instance ít |
| Một số tenant lớn cần cách ly | Shared + các dedicated breakers | Dung hòa isolation và cardinality |
| Traffic đa vùng tới backend riêng | Thêm vùng vào scope | Sự cố một vùng không khóa vùng khác |
| Mỗi request có SKU/request ID riêng | **Không dùng làm key** | Không phải miền lỗi; key tăng không giới hạn |

Không có một sơ đồ cố định cho mọi hệ thống. Phạm vi cần xuất phát từ cách triển khai và cơ chế lỗi thực tế của dependency, sau đó kiểm chứng bằng traffic và tình huống sự cố.

## 6. Triển khai đơn giản với native advice theo endpoint

**RequestHandlerCircuitBreakerAdvice** của Spring Integration gắn với request handler và giữ trạng thái breaker trên instance advice. Khi có hai dependency độc lập, khai báo **hai instance advice độc lập**.

Ví dụ cấu hình minh họa (các import lược bớt):

~~~java
@Configuration
@EnableIntegration
public class EndpointBreakerConfig {

    @Bean
    public RequestHandlerCircuitBreakerAdvice stockReadAdvice() {
        RequestHandlerCircuitBreakerAdvice advice =
                new RequestHandlerCircuitBreakerAdvice();
        advice.setThreshold(3);
        advice.setHalfOpenAfter(15_000);
        return advice;
    }

    @Bean
    public RequestHandlerCircuitBreakerAdvice pricingReadAdvice() {
        RequestHandlerCircuitBreakerAdvice advice =
                new RequestHandlerCircuitBreakerAdvice();
        advice.setThreshold(3);
        advice.setHalfOpenAfter(15_000);
        return advice;
    }

    @Bean
    public IntegrationFlow stockReadFlow(
            StockClient stockClient,
            RequestHandlerCircuitBreakerAdvice stockReadAdvice
    ) {
        return IntegrationFlow.from("stock.read.requests")
                .handle(
                        StockQuery.class,
                        (query, headers) -> stockClient.lookup(query),
                        endpoint -> endpoint.advice(stockReadAdvice)
                )
                .get();
    }

    @Bean
    public IntegrationFlow pricingReadFlow(
            PricingClient pricingClient,
            RequestHandlerCircuitBreakerAdvice pricingReadAdvice
    ) {
        return IntegrationFlow.from("pricing.read.requests")
                .handle(
                        PriceQuery.class,
                        (query, headers) -> pricingClient.lookup(query),
                        endpoint -> endpoint.advice(pricingReadAdvice)
                )
                .get();
    }
}
~~~

Trong ví dụ, **StockClient**, **PricingClient**, **StockQuery** và **PriceQuery** là các kiểu ứng dụng tự định nghĩa. Mỗi advice quan sát exception từ handler tương ứng. Không vô tình truyền **cùng một advice instance** cho cả hai endpoint nếu muốn hai breaker độc lập.

Native advice thuận tiện khi số endpoint ít và chỉ cần ngưỡng lỗi liên tiếp cùng khoảng chờ. Nếu muốn cấp breaker theo các tenant động, có thể phải quản lý việc tạo/routing nhiều handler/advice hoặc chọn thư viện có **registry định danh instance** để dễ kiểm soát hơn.

## 7. Spring Integration + Resilience4j với registry phân vùng

Resilience4j hỗ trợ tạo nhiều instance circuit breaker theo **name** thông qua **CircuitBreakerRegistry**. Những lời gọi dùng cùng name trong một registry sẽ nhận cùng một breaker; name khác có trạng thái riêng.

Một thiết kế dễ kiểm soát là dùng tập **scope hữu hạn** cho endpoint và nhóm tenant. Ví dụ chỉ cho phép một số tenant đặc biệt có breaker riêng; những tenant khác dùng shared breaker.

### 7.1. Hợp đồng message và scope đã xác thực

~~~java
public record StockQuery(String sku) {}

public record StockResult(String sku, int availableUnits) {}

public interface StockClient {
    StockResult lookup(String tenantId, String sku);
}

public enum TenantCircuitGroup {
    SHARED,
    DEDICATED_A,
    DEDICATED_B
}

public record VerifiedTenantContext(
        String tenantId,
        TenantCircuitGroup group
) {}

public interface VerifiedTenantResolver {
    VerifiedTenantContext resolveFromTrustedContext(
            Map<String, Object> headers);
}
~~~

**VerifiedTenantResolver** là interface cần được ứng dụng triển khai tại ranh giới bảo mật. Nó phải lấy tenant từ **identity đã xác thực** hoặc ngữ cảnh được dịch vụ tin cậy gắn vào message, kiểm tra quyền và ánh xạ tenant sang một trong ba group. Không được chỉ đọc một header **tenantId** do caller bên ngoài tự gửi rồi cho rằng đó là tenant hợp lệ.

**TenantCircuitGroup** là phạm vi breaker, còn **tenantId** vẫn là định danh dữ liệu dùng khi StockClient thực thi. Việc nhiều tenant chung group **không có nghĩa** được phép dùng chung cache, credential hoặc dữ liệu trả về.

### 7.2. Registry với cấu hình có số mẫu tối thiểu

~~~java
@Configuration
@EnableIntegration
@IntegrationComponentScan
public class StockBreakerConfiguration {

    @Bean
    public CircuitBreakerRegistry stockCircuitBreakerRegistry() {
        CircuitBreakerConfig config = CircuitBreakerConfig.custom()
                .slidingWindowType(
                        CircuitBreakerConfig.SlidingWindowType.COUNT_BASED)
                .slidingWindowSize(20)
                .minimumNumberOfCalls(10)
                .failureRateThreshold(50.0f)
                .waitDurationInOpenState(Duration.ofSeconds(20))
                .permittedNumberOfCallsInHalfOpenState(2)
                .build();

        return CircuitBreakerRegistry.of(config);
    }

    @Bean
    public IntegrationFlow stockReadFlow(PartitionedStockCaller caller) {
        return IntegrationFlow.from("stock.read.requests")
                .handle(
                        StockQuery.class,
                        (query, headers) -> caller.lookup(query, headers)
                )
                .get();
    }
}

@MessagingGateway(defaultRequestChannel = "stock.read.requests")
public interface StockGateway {
    StockResult lookup(StockQuery query);
}
~~~

Cấu hình minh họa dùng **minimumNumberOfCalls(10)** để tránh mở circuit dựa trên một vài request. Con số thực tế phải dựa trên traffic. Đối với dedicated tenant rất ít request, một ngưỡng như vậy có thể khiến breaker không đủ mẫu để mở trong thời gian mong muốn; cần cân nhắc phạm vi và window cẩn thận.

### 7.3. Chọn breaker theo scope trước lời gọi client

~~~java
@Component
public class PartitionedStockCaller {

    private final CircuitBreakerRegistry registry;
    private final VerifiedTenantResolver tenantResolver;
    private final StockClient stockClient;

    public PartitionedStockCaller(
            CircuitBreakerRegistry registry,
            VerifiedTenantResolver tenantResolver,
            StockClient stockClient
    ) {
        this.registry = registry;
        this.tenantResolver = tenantResolver;
        this.stockClient = stockClient;
    }

    public StockResult lookup(
            StockQuery query,
            Map<String, Object> headers
    ) {
        VerifiedTenantContext tenant =
                tenantResolver.resolveFromTrustedContext(headers);

        // Tập key bị giới hạn bởi enum đã kiểm soát.
        String breakerName =
                "stock.read:" + tenant.group().name();

        CircuitBreaker breaker =
                registry.circuitBreaker(breakerName);

        return breaker.executeSupplier(
                () -> stockClient.lookup(tenant.tenantId(), query.sku())
        );
    }
}
~~~

Trong đoạn mã này:

1. Gateway chuyển message sang channel **stock.read.requests**.
2. Resolver lấy **tenant đã xác thực** và chọn group từ cấu hình chính sách nội bộ.
3. Registry tìm hoặc tạo breaker ứng với tên ổn định như **stock.read:DEDICATED_A**.
4. Supplier chỉ bao thao tác **StockClient.lookup**, để exception của dependency được breaker ghi nhận chính xác.
5. Khi breaker OPEN, supplier không chạy; lỗi không được cấp quyền có thể truyền về Gateway để xử lý fail fast hoặc fallback ngoài breaker.

Ví dụ chọn ba group nhằm minh họa **bounded cardinality**. Nó chưa triển khai resolver hay StockClient thực tế: đây là những adapter do ứng dụng cung cấp. Nếu cần **mỗi tenant có breaker độc lập**, ánh xạ phải bảo đảm **mỗi tenant riêng được cấp một group/key riêng**, kèm chính sách giới hạn số breaker, vòng đời và quan sát. Không thể gọi ba group trên là “breaker per tenant” cho mọi tenant trong hệ thống.

### 7.4. Thêm endpoint vào key mà không làm nổ số lượng

Nếu cùng một registry quản lý nhiều endpoint logic, có thể tạo key từ hai tập giá trị đã được kiểm soát:

~~~java
public enum DependencyOperation {
    STOCK_READ,
    STOCK_RESERVE,
    PRICING_READ
}

public record CircuitScope(
        DependencyOperation operation,
        TenantCircuitGroup group
) {
    public String breakerName() {
        return operation.name() + ":" + group.name();
    }
}
~~~

Tối đa 3 operation × 3 group = **9 scope logic** trong ví dụ. Một endpoint không cần phân vùng tenant có thể luôn dùng **SHARED**, giảm thêm số instance thực tế.

Các endpoint có SLO khác nhau có thể đăng ký **CircuitBreakerConfig khác nhau** khi tạo instance. Cấu hình shared/global không nhất thiết phù hợp với read latency 100 ms và reserve latency 3 giây; việc chọn timeout, error threshold và wait duration phải dựa trên dependency/operation thực tế.

## 8. Quản lý số lượng breaker: tránh cardinality không giới hạn

Lợi ích cô lập có thể trở thành chi phí lớn khi tạo breaker tùy ý theo tenant động.

Ví dụ nếu có **20 endpoint × 50.000 tenant**, một tổ hợp endpoint-tenant đầy đủ có thể tạo tới **1.000.000 key**. Registry, event listener, metrics, object thống kê và các tham chiếu có thể tiêu tốn nhiều bộ nhớ. Nhiều key còn làm phình số chuỗi metric và giảm hiệu quả giám sát.

Các biện pháp cần cân nhắc:

- **Phân nhóm theo miền lỗi thực:** chỉ cấp breaker riêng cho tenant có quota, provider hoặc hạ tầng thật sự độc lập.
- **Whitelist / scope policy:** quyết định các tenant dedicated dựa trên cấu hình đã xác thực và được kiểm soát, không lấy tên tùy ý từ request.
- **Giới hạn số instance:** nếu hỗ trợ tenant động, cần ngân sách số breaker và chính sách hết hạn/dọn dẹp rõ ràng cho tenant không còn hoạt động.
- **Cơ chế loại bỏ an toàn:** chỉ dọn khi không còn lời gọi đang sử dụng breaker, không phá state một cách đột ngột hoặc làm lộ tài nguyên listener/metrics.
- **Metric aggregation:** tránh dùng tenant ID, SKU, request ID, correlation ID làm tag có cardinality cao. Dùng bucket, endpoint và outcome; tenant ID cần điều tra có thể nằm trong log/trace có kiểm soát.
- **Tách theo mức ưu tiên:** một số tenant quan trọng có dedicated breaker; nhóm nhỏ còn lại dùng breaker chung và per-tenant rate limiter để kiểm soát sự công bằng.

Không nên giả định registry tự xóa instance sau khi tenant không còn request. Vòng đời, dọn metric/registry và cập nhật config cần được kiểm chứng theo phiên bản thư viện và kiến trúc ứng dụng.

### Tránh dùng key chứa dữ liệu nhạy cảm

Breaker name thường được xuất hiện trong metric, log hoặc dashboard. Nếu tạo name bằng email, mã khách hàng nhạy cảm hoặc giá trị tenant nội bộ, dữ liệu đó có thể bị lộ qua kênh giám sát. Dùng tên group trung tính hoặc định danh kỹ thuật đã được phép xuất hiện trong hệ thống quan sát.

## 9. Failure count khi nhiều tenant chia chung breaker

Giả sử breaker **stock.read:SHARED** có ngưỡng ba lỗi liên tiếp và dùng chung cho tenant T1, T2, T3:

| Request | Tenant | Kết quả | Lỗi liên tiếp của breaker SHARED |
| --- | --- | --- | ---: |
| 1 | T1 | Timeout | 1 |
| 2 | T2 | Timeout | 2 |
| 3 | T3 | Timeout | 3, mạch OPEN |
| 4 | T1 | Bị từ chối | Không gọi client |
| 5 | T2 | Bị từ chối | Không gọi client |

Tất cả tenant trong nhóm shared chịu tác động của cùng trạng thái. Đây là hệ quả trực tiếp của việc dùng chung instance, không phải bug của breaker.

Khi chia theo tenant riêng:

~~~mermaid
flowchart LR
    A[Tenant A] --> B[Breaker A: OPEN]
    C[Tenant B] --> D[Breaker B: CLOSED]
    B -.-> E[Chặn lời gọi A]
    D --> F[Cho B gọi upstream]
~~~

Tenant B có thể tiếp tục, **nếu upstream của B thực sự khỏe và có tài nguyên độc lập**. Nếu upstream chung đang hỏng, A và B sẽ tự ghi nhận lỗi theo các cửa sổ riêng; B có thể mất một số lần gọi trước khi breaker B mở.

**Vấn đề ít traffic:** một tenant chỉ gọi hai lần mỗi giờ, trong khi breaker cần tối thiểu mười lời gọi để xét failure rate, có thể rất lâu mới đạt minimum number of calls. Có thể dùng count-based consecutive failures với ngưỡng nhỏ hơn, gộp tenant thành nhóm hoặc điều chỉnh SLO chính sách. Tuy nhiên ngưỡng quá nhỏ lại gây mở mạch vì nhiễu.

## 10. Tương tác với retry, timeout, bulkhead và rate limiter

Circuit breaker chỉ có khả năng suy ra tình trạng lỗi từ các **kết quả nó quan sát được**. Nếu mỗi tenant có breaker riêng nhưng tất cả cùng dùng một HTTP connection pool, sự cố của tenant A vẫn có thể làm cạn pool và khiến tenant B bị chậm.

Do đó phạm vi breaker cần phối hợp với các giới hạn tài nguyên:

| Cơ chế | Vấn đề giải quyết | Phạm vi có thể cần |
| --- | --- | --- |
| **Timeout** | Giới hạn thời gian một lời gọi đang chạy | Theo endpoint/dependency và SLA |
| **Circuit breaker** | Ngắt lời gọi mới sau chuỗi/tỷ lệ lỗi | Theo miền lỗi endpoint/tenant |
| **Bulkhead** | Giới hạn số lời gọi hoặc tài nguyên đồng thời | Theo dependency hoặc nhóm tenant |
| **Rate limiter** | Giới hạn tốc độ truy cập/quota | Có thể theo tenant |
| **Retry** | Thử lại lỗi tạm thời | Theo tính idempotent của operation |

### Retry thay đổi các thống kê trong từng scope

Nếu breaker bao ngoài retry, một request logic có nhiều attempt có thể tạo **một kết quả cuối** cho breaker. Nếu retry bao ngoài breaker, từng attempt có thể được thống kê ở scope của breaker. Dù đặt theo tenant hay endpoint, cần xác định rõ đơn vị đo để không làm circuit của một tenant mở quá nhanh vì retry nhiều lần.

Không retry vô hạn khi breaker OPEN. Trong Resilience4j, lời gọi bị từ chối có thể tạo **CallNotPermittedException**; không coi exception đó như một request lỗi mới ở dependency để tiếp tục retry.

### Tác vụ ghi phải có idempotency

Đối với operation như **stock.reserve**, một lần timeout không chứng minh upstream chưa xử lý lệnh. Nếu retry hoặc replay từ queue, cần **idempotency key** riêng theo request nghiệp vụ, được kiểm soát theo tenant để không gây trùng đơn hoặc giữ hàng nhiều lần.

### OPEN → HALF_OPEN theo từng breaker

Mỗi scope có thời gian chờ và HALF_OPEN của riêng nó. Nếu có nhiều breaker OPEN cùng lúc do outage toàn vùng, chúng có thể đồng thời cho phép probe khi hết wait duration. Cần giới hạn số probe, concurrency và tổng traffic phục hồi ở cấp dependency, nhất là khi upstream có thể quá tải sau khi vừa hồi phục.

## 11. Fallback phải đúng tenant và đúng loại endpoint

Khi breaker OPEN, Spring Integration không tự quyết định kết quả nghiệp vụ. Các nhánh cần fallback tường minh và an toàn.

| Scope | Khi OPEN | Phương án phù hợp |
| --- | --- | --- |
| **stock.read** trên màn hình danh mục | Chưa lấy được dữ liệu mới | Cache tham khảo còn TTL, gắn nhãn stale |
| **stock.reserve** khi xác nhận đơn | Không thể xác nhận giữ hàng | Fail fast/UNAVAILABLE; không coi đơn hoàn tất |
| **pricing.read** có dữ liệu giá cho phép dùng cũ | API chậm hoặc lỗi | Cache có nguồn gốc và thời hạn riêng |
| **notification.send** bất đồng bộ | Provider chưa phục hồi | Queue/outbox bền vững và replay có giới hạn |

Ở đa tenant, **fallback data phải được phân vùng theo tenant**, kể cả khi breaker chung một group. Ví dụ không được dùng cache key chỉ có **SKU** nếu tồn kho khác nhau theo tenant/kho. Key phải bao gồm định danh tenant đã xác thực và các chiều nghiệp vụ quan trọng, đồng thời enforce phân quyền trước khi đọc cache.

Outcome nên biểu diễn rõ:

~~~java
public enum LookupStatus {
    FRESH,
    STALE_REFERENCE,
    UNAVAILABLE
}

public record StockLookupReply(
        String tenantId,
        String sku,
        LookupStatus status,
        Integer availableUnits,
        Instant sourceTime,
        String correlationId,
        String reasonCode
) {}
~~~

**UNAVAILABLE** là “chưa có dữ liệu đáng tin cậy”, không đồng nghĩa “hết hàng”. Khi fallback nằm **ngoài vùng thực thi breaker**, breaker vẫn ghi nhận failure của StockClient trước khi trả dữ liệu cache hoặc lỗi phù hợp.

Không được lấy tenantId trong outcome như bằng chứng đã xác thực; đây chỉ là metadata để đối soát. Việc quyền truy cập vào tenant nào được quyết định ở ingress/Resolver tin cậy.

## 12. Error channel, Router, Splitter, Aggregator và correlation

### Router

Router có thể chọn operation như stock.read, stock.reserve hoặc pricing.read. Breaker key là quyết định hạ tầng dựa trên operation và miền lỗi; Router phải tiếp tục tôn trọng ý nghĩa nghiệp vụ của message. Nếu một nhánh đang OPEN, không tự route yêu cầu giữ hàng sang nhánh đọc dữ liệu cache như thể hành vi hai nhánh tương đương.

### Gateway đồng bộ

Với Gateway gọi qua **DirectChannel**, exception từ handler hoặc Resilience4j có thể truyền thẳng về caller. Lớp API cần ánh xạ lỗi theo scope: ví dụ **Stock của tenant A tạm không khả dụng**. Không tiết lộ cấu trúc tenant khác hoặc trạng thái breaker của người dùng không có quyền.

### Error channel bất đồng bộ

Khi handler chạy qua ExecutorChannel/poller/adapter bất đồng bộ, lỗi có thể tạo **ErrorMessage** theo cơ chế error channel tương ứng. Error flow cần đủ thông tin để quyết định retry/defer:

- Tenant đã xác thực.
- Endpoint/operation logic và breaker scope đã chọn.
- Correlation/trace ID và idempotency key nếu có.
- Exception gốc hoặc reason code, đặc biệt phân biệt **dependency failure** với **breaker rejected**.

Một error channel không tự bảo đảm mọi lỗi đồng bộ từ Gateway sẽ đi vào đó. Cần xác minh boundary thực thi thực tế.

### Splitter và Aggregator

Khi Splitter tạo nhiều request con từ một đơn hàng, chúng có thể đi qua breaker khác nhau theo operation, vùng hoặc tenant. Nếu một nhánh bị OPEN và không trả reply, Aggregator có thể chờ thiếu message.

Cần giữ **correlation ID**, **sequence metadata** và **tenant context đã xác thực** trên từng nhánh. Định nghĩa rõ partial result, fallback outcome, group timeout, expiration và discard/error path. Không gộp message của các tenant khác nhau chỉ vì cùng correlation ID do client cung cấp; nên có khóa nhóm hoặc bước xác thực ngữ cảnh đủ để tách biệt request của tenant.

## 13. Kiểm thử sự cô lập giữa hai breaker

Bài test cần chứng minh rằng breaker của scope A OPEN **không tự làm breaker B OPEN**, đồng thời request bị chặn không đi tới dependency. Có thể dùng Resilience4j và fake client với bộ đếm riêng.

~~~java
@Test
void outageInOneTenantScopeDoesNotOpenAnotherScope() {
    CircuitBreakerConfig config = CircuitBreakerConfig.custom()
            .slidingWindowSize(2)
            .minimumNumberOfCalls(2)
            .failureRateThreshold(100.0f)
            .waitDurationInOpenState(Duration.ofSeconds(30))
            .build();

    CircuitBreakerRegistry registry = CircuitBreakerRegistry.of(config);
    CircuitBreaker tenantA = registry.circuitBreaker(
            "stock.read:DEDICATED_A");
    CircuitBreaker tenantB = registry.circuitBreaker(
            "stock.read:DEDICATED_B");

    AtomicInteger callsA = new AtomicInteger();
    AtomicInteger callsB = new AtomicInteger();

    Supplier<String> failingA = () -> {
        callsA.incrementAndGet();
        throw new IllegalStateException("tenant A upstream unavailable");
    };
    Supplier<String> healthyB = () -> {
        callsB.incrementAndGet();
        return "OK";
    };

    assertThrows(
            IllegalStateException.class,
            () -> tenantA.executeSupplier(failingA));
    assertThrows(
            IllegalStateException.class,
            () -> tenantA.executeSupplier(failingA));

    assertEquals(CircuitBreaker.State.OPEN, tenantA.getState());
    assertThrows(
            CallNotPermittedException.class,
            () -> tenantA.executeSupplier(failingA));
    assertEquals(2, callsA.get());

    assertEquals("OK", tenantB.executeSupplier(healthyB));
    assertEquals(CircuitBreaker.State.CLOSED, tenantB.getState());
    assertEquals(1, callsB.get());
}
~~~

Các import thông thường được lược bớt. Đây là test về **trạng thái breaker riêng biệt**, không kiểm chứng rằng hai tenant có backend thực sự độc lập. Test tích hợp cần fake provider trả lỗi riêng cho tenant A, thành công cho tenant B, đồng thời chạy message qua Gateway và route resolver thật.

### Ma trận kiểm thử cần có

| Tình huống | Kết quả cần xác minh |
| --- | --- |
| Stock.read lỗi, Pricing.read khỏe | Stock breaker OPEN không tự chặn Pricing |
| Read lỗi, Reserve khỏe trên hạ tầng độc lập | Breaker của operation read không tự mở breaker reserve |
| Tenant A lỗi, B khỏe, key riêng | A OPEN; B vẫn có quyền gọi |
| Tenant A/B cùng SHARED | Lỗi đủ ngưỡng có thể làm OPEN cho cả nhóm |
| Tenant chưa được xác thực | Bị từ chối trước khi tạo breaker hoặc gọi dependency |
| Tenant ID lạ / request có key giả | Không tạo breaker mới từ input tùy ý |
| Nhiều tenant traffic thấp | Minimum calls và cửa sổ không khiến mạch phản ứng sai mong muốn |
| Cùng name breaker trong registry | Các lời gọi dùng chung state như thiết kế |
| Khác name breaker | Trạng thái, counter được cách ly |
| Breaker OPEN | Call counter của đúng client không tăng |
| HALF_OPEN nhiều scope | Giới hạn permit và tổng tải phục hồi |
| Cache fallback của A | Không đọc/trả dữ liệu tenant B |
| Splitter/Aggregator nhiều nhánh | Correlation và tenant không bị trộn; group kết thúc theo policy |
| Nhiều instance/pod | Không giả định một breaker state toàn cục |

Các test timeout/retry phải dùng fake có thể điều khiển exception, độ trễ và số attempt; không chỉ assert Gateway có lỗi. Với lỗi thao tác ghi, thêm test idempotency và replay để bảo đảm không tạo side effect hai lần.

## 14. Quan sát và vận hành breaker theo scope

Một hệ thống nhiều breaker khó bảo trì nếu không có sơ đồ phạm vi, naming convention và metrics nhất quán.

| Tín hiệu | Theo dõi gì? |
| --- | --- |
| **breaker name / scope** | Operation hoặc nhóm tenant nào đang OPEN? |
| **state transition** | Thời điểm mở, thăm dò, đóng lại theo scope |
| **failure / slow call rate** | Nhóm nào có lỗi hoặc latency bất thường? |
| **not-permitted calls** | Scope nào đang từ chối nhiều message? |
| **request rate và minimum calls** | Breaker có đủ mẫu để mở không? |
| **Gateway latency / channel queue depth** | Flow có bị nghẽn dù breaker đã OPEN? |
| **fallback rate / cache age** | Tenant nào đang dùng kết quả suy giảm và có còn an toàn không? |
| **bulkhead saturation / rate-limit rejection** | Có tenant nào làm cạn tài nguyên chung không? |
| **Aggregator group timeout** | Nhánh OPEN có làm thiếu reply hay không? |

Với Resilience4j, có thể tích hợp Micrometer và event publisher. Nên dùng metric tags có cardinality giới hạn như **operation**, **region đã chuẩn hóa**, **tenant group** và **outcome**. Nếu thật sự cần điều tra một tenant, dùng log/trace có phân quyền với tenant ID và correlation ID; không tạo một time series cho mỗi request hoặc mọi tenant không giới hạn.

**Trạng thái thường nằm trong process.** Các pod có thể mở/đóng breaker ở thời điểm khác nhau do traffic khác nhau. Nếu cần chính sách hạn chế traffic chung toàn hệ thống, bổ sung rate limiter hoặc cơ chế điều phối phù hợp; không giả định Resilience4j tự chia sẻ trạng thái breaker giữa các pod.

### Những dấu hiệu chọn scope sai

- **Một endpoint lỗi kéo cả nhánh khác xuống:** breaker dùng chung rộng quá mức hoặc tài nguyên chung không được cách ly.
- **Lỗi upstream rõ rệt nhưng không breaker nào OPEN:** phạm vi quá nhỏ, thiếu minimum calls hoặc lỗi không được record.
- **Số breaker tăng liên tục:** key lấy từ dữ liệu request động; registry/lifecycle không được giới hạn.
- **Metric có quá nhiều series:** tenant ID/SKU/request ID được gắn làm tag; dashboard tốn tài nguyên.
- **Tenant B vẫn chậm dù breaker A OPEN:** pool/concurrency/quota chung, cần bulkhead/rate limiter ngoài breaker.
- **Một tenant nhận cache của tenant khác:** lỗi phân vùng dữ liệu, cần xử lý tại cache/identity boundary; breaker scope không thay thế authorization.

## 15. Checklist áp dụng

- [ ] Đã xác định **miền lỗi** thực tế trước khi chọn breaker per service, endpoint, region hay tenant.
- [ ] Key dùng **operation/region/tenant group ổn định**, không chứa URL động, SKU hay request ID.
- [ ] Tenant context được xác thực ở ingress và giữ nguyên qua message headers/correlation.
- [ ] Dùng breaker riêng cho dependency độc lập; native advice không bị chia sẻ instance ngoài ý muốn.
- [ ] Nếu dùng Registry, có giới hạn số key, chiến lược lifecycle và chính sách dọn metrics/listeners.
- [ ] Chọn minimum calls, cửa sổ, timeout, retry và HALF_OPEN probe theo từng scope đủ traffic.
- [ ] Có rate limiter/bulkhead khi nhiều tenant dùng tài nguyên chung.
- [ ] Fallback và cache có phân quyền, TTL và khóa dữ liệu theo tenant; không nhầm UNAVAILABLE với kết quả nghiệp vụ.
- [ ] Gateway/error channel, Router, Splitter và Aggregator giữ correlation và tenant context đúng.
- [ ] Kiểm thử A lỗi/B khỏe, group shared, request bị từ chối, trường hợp tenant giả và cache isolation.
- [ ] Quan sát metric theo scope bounded cardinality; dùng log/trace có kiểm soát cho ID chi tiết.

**Circuit breaker theo endpoint hoặc tenant** giúp ngắt lỗi tại đúng phạm vi thay vì để một dependency hay tenant không khỏe kéo cả hệ thống xuống. Trong Spring Integration, phạm vi breaker phải đi cùng Router, Gateway, error channel, correlation, giới hạn tài nguyên và cách phân vùng dữ liệu. Chọn một số lượng breaker có thể quản trị, đặt chúng sát điểm gọi dependency và kiểm thử cô lập thực tế sẽ giúp flow vừa ít phụ thuộc vừa phục hồi có kiểm soát.
