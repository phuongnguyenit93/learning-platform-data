# Trang trí Mono hoặc Flux qua API chung

## Mục tiêu của bài học

Trong ứng dụng Spring WebFlux, lời gọi đến dịch vụ phụ thuộc thường trả về một publisher của Reactor: Mono biểu diễn tối đa một kết quả, còn Flux biểu diễn một chuỗi gồm không, một hoặc nhiều phần tử. Khi một dịch vụ từ xa chậm hoặc không khả dụng, circuit breaker cần bảo vệ lời gọi bất đồng bộ mà không làm mất đặc tính reactive của luồng xử lý.

Spring Cloud CircuitBreaker cung cấp API chung để ứng dụng tạo và sử dụng reactive circuit breaker. Với API này, bạn có thể bọc một Mono cùng hàm fallback. Khi cần bảo vệ một Flux, cần hiểu rõ ranh giới của API chung và cách dùng operator Reactor của Resilience4j. Phân biệt hai cách này giúp chọn đúng abstraction, giữ được streaming và tránh vô tình biến một luồng dữ liệu lớn thành một tập hợp phải nạp hết vào bộ nhớ.

Sau bài học, bạn có thể:

- Phân biệt Mono và Flux trong ngữ cảnh lời gọi đến dịch vụ phụ thuộc.
- Dùng ReactiveCircuitBreakerFactory để bảo vệ một Mono và cung cấp fallback.
- Dùng CircuitBreakerOperator để trang trí một Mono hoặc Flux với Resilience4j Reactor.
- Đặt fallback đúng vị trí trong chuỗi operator để breaker vẫn ghi nhận lỗi.
- Hiểu một subscription được tính như thế nào và vì sao stream dài cần cách bảo vệ phù hợp.
- Kiểm tra hành vi khi breaker đóng, mở và thử phục hồi trong ứng dụng reactive.

## 1. Mono và Flux trong một lời gọi từ xa

Reactor là thư viện reactive được Spring WebFlux sử dụng. Hai kiểu dữ liệu cơ bản thường gặp là:

| Kiểu | Số phần tử | Ví dụ |
| --- | --- | --- |
| Mono<T> | Tối đa một phần tử, hoặc hoàn tất rỗng, hoặc phát sinh lỗi. | Tra cứu một sản phẩm theo mã; lấy thông tin tồn kho. |
| Flux<T> | Không, một hoặc nhiều phần tử; có thể phát liên tục cho đến khi hoàn tất hoặc lỗi. | Lấy danh sách sản phẩm; nhận luồng sự kiện; đọc dữ liệu phân trang hoặc stream. |

WebClient cung cấp các phương thức tạo publisher từ HTTP response. bodyToMono(Product.class) trả về Mono<Product>; bodyToFlux(Product.class) trả về Flux<Product>. Việc tạo publisher thường chưa gửi request ngay. Với publisher lạnh (cold publisher), request được thực hiện khi có subscription.

Một lời gọi đến inventory-service thường trả về một kết quả nên phù hợp với Mono:

    Mono<InventoryResponse> response = webClient.get()
        .uri("/inventory/{sku}", sku)
        .retrieve()
        .bodyToMono(InventoryResponse.class);

Một lời gọi lấy danh sách hoặc luồng dữ liệu có thể trả về Flux:

    Flux<Product> products = webClient.get()
        .uri("/products")
        .retrieve()
        .bodyToFlux(Product.class);

Circuit breaker bảo vệ thao tác gọi phụ thuộc, không phải từng phần tử dữ liệu một cách mặc định. Khi trang trí publisher, hãy xác định một subscription đại diện cho một lần gọi HTTP, một luồng streaming hay một tác vụ nghiệp vụ. Ranh giới này quyết định dữ liệu thống kê của breaker có ý nghĩa hay không.

## 2. API reactive chung của Spring Cloud CircuitBreaker

Spring Cloud CircuitBreaker cung cấp ReactiveCircuitBreakerFactory để tạo breaker theo tên. API ReactiveCircuitBreaker phổ biến nhận một Mono cùng hàm fallback trả về Mono. Ví dụ:

    import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
    import org.springframework.stereotype.Service;
    import org.springframework.web.reactive.function.client.WebClient;
    import reactor.core.publisher.Mono;

    @Service
    public class ReactiveInventoryGateway {

        private final WebClient webClient;
        private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;

        public ReactiveInventoryGateway(
                WebClient webClient,
                ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
            this.webClient = webClient;
            this.circuitBreakerFactory = circuitBreakerFactory;
        }

        public Mono<InventoryResponse> find(String sku) {
            Mono<InventoryResponse> request = webClient.get()
                .uri("/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryResponse.class);

            return circuitBreakerFactory.create("inventory").run(
                request,
                error -> Mono.just(InventoryResponse.unknown(sku))
            );
        }
    }

Trong ví dụ:

- create("inventory") lấy reactive circuit breaker có tên inventory. Tên này liên kết lời gọi với cấu hình và số liệu tương ứng.
- request là publisher thực hiện HTTP request khi được subscribe.
- run nhận publisher chính và hàm fallback. Fallback trả về Mono cùng kiểu dữ liệu với publisher chính.
- InventoryResponse.unknown(sku) là phương thức do ứng dụng tự định nghĩa, dùng để biểu diễn trạng thái chưa xác định; đây không phải lớp có sẵn của Spring.

Khi breaker đang CLOSED, lời gọi được chuyển tiếp và kết quả được ghi nhận. Nếu lỗi được ghi nhận vượt ngưỡng, breaker có thể chuyển OPEN. Trong trạng thái OPEN, lời gọi tiếp theo bị từ chối nhanh và hàm fallback có thể tạo phản hồi thay thế. Sau thời gian chờ, breaker chuyển sang HALF_OPEN để cho phép một số lời gọi thử nghiệm. Kết quả các lần thử quyết định breaker trở về CLOSED hay mở lại.

Fallback phải phù hợp với nghiệp vụ. Nếu không truy vấn được tồn kho, trả về UNKNOWN có thể an toàn hơn việc khẳng định sản phẩm còn hàng hoặc hết hàng. Một fallback khác có thể dùng dữ liệu cache còn hạn, hoặc trả lỗi nghiệp vụ để tầng API yêu cầu người dùng thử lại. Không gọi lại chính inventory-service bên trong fallback vì điều đó có thể tạo vòng lặp và tiếp tục gây tải lên phụ thuộc đang lỗi.

API chung ở đây hướng đến Mono. Không nên giả định ReactiveCircuitBreaker.run có overload nhận trực tiếp Flux trong mọi phiên bản Spring Cloud CircuitBreaker. Khi cần bảo vệ Flux, hãy dùng operator tương ứng của implementation reactive, hoặc tạo một lớp adapter của ứng dụng để cung cấp giao diện thống nhất.

## 3. Trang trí Mono hoặc Flux bằng Resilience4j Reactor

Resilience4j cung cấp operator Reactor để trang trí publisher. CircuitBreakerOperator có thể được dùng với Mono và Flux. Operator này áp dụng một Resilience4j CircuitBreaker lên quá trình subscribe và các tín hiệu kết thúc của publisher.

Ví dụ dưới đây minh họa cách lấy CircuitBreaker từ CircuitBreakerRegistry và bảo vệ Flux:

    import io.github.resilience4j.circuitbreaker.CircuitBreaker;
    import io.github.resilience4j.circuitbreaker.CircuitBreakerRegistry;
    import io.github.resilience4j.reactor.circuitbreaker.operator.CircuitBreakerOperator;
    import org.springframework.stereotype.Service;
    import org.springframework.web.reactive.function.client.WebClient;
    import reactor.core.publisher.Flux;

    @Service
    public class ReactiveProductGateway {

        private final WebClient webClient;
        private final CircuitBreaker productStreamBreaker;

        public ReactiveProductGateway(
                WebClient webClient,
                CircuitBreakerRegistry registry) {
            this.webClient = webClient;
            this.productStreamBreaker = registry.circuitBreaker("product-stream");
        }

        public Flux<Product> list() {
            return webClient.get()
                .uri("/products")
                .retrieve()
                .bodyToFlux(Product.class)
                .transformDeferred(
                    CircuitBreakerOperator.of(productStreamBreaker)
                );
        }
    }

CircuitBreakerRegistry là registry của Resilience4j. Trong ứng dụng Spring Boot đã tích hợp Resilience4j, registry thường được cấu hình và cung cấp qua cơ chế auto-configuration tương ứng. Nếu tự tạo registry, hãy bảo đảm cấu hình instance của ứng dụng và registry được dùng nhất quán. Dependency cần có operator Reactor của Resilience4j; với Spring Cloud CircuitBreaker reactive starter, hãy kiểm tra dependency được resolve để xác nhận module reactor có mặt.

transformDeferred áp dụng operator cho publisher tại thời điểm subscribe. Cách này phù hợp với publisher reactive lạnh và giúp ranh giới bảo vệ gắn với từng subscription. CircuitBreakerOperator không thay đổi kiểu dữ liệu: Mono vẫn là Mono và Flux vẫn là Flux.

Có thể dùng cùng operator với Mono:

    public Mono<Product> find(String id) {
        CircuitBreaker breaker = registry.circuitBreaker("product-detail");

        return webClient.get()
            .uri("/products/{id}", id)
            .retrieve()
            .bodyToMono(Product.class)
            .transformDeferred(CircuitBreakerOperator.of(breaker));
    }

Ví dụ này sử dụng trực tiếp Resilience4j Reactor operator. Nếu dự án muốn giữ phụ thuộc vào abstraction của Spring Cloud, hãy cân nhắc dùng ReactiveCircuitBreakerFactory cho Mono. Với Flux, có thể bọc cách dùng CircuitBreakerOperator trong adapter riêng của ứng dụng để phần nghiệp vụ gọi một API nội bộ thống nhất.

## 4. Tạo API ứng dụng thống nhất cho Mono và Flux

Trong một codebase có cả lời gọi trả về Mono và Flux, nhóm phát triển có thể muốn một facade chung. Facade này là API do ứng dụng định nghĩa; nó không phải một overload mặc định của ReactiveCircuitBreaker trong Spring Cloud.

Ví dụ, hợp đồng nội bộ có thể tách hai phương thức theo kiểu publisher:

    public interface ReactiveCallProtection {

        <T> Mono<T> protectMono(
            String name,
            Mono<T> source,
            Function<Throwable, Mono<T>> fallback
        );

        <T> Flux<T> protectFlux(
            String name,
            Flux<T> source
        );
    }

Một implementation có thể dùng ReactiveCircuitBreakerFactory cho Mono và CircuitBreakerRegistry cùng CircuitBreakerOperator cho Flux. Khi đó, các gateway chỉ phụ thuộc vào ReactiveCallProtection; chi tiết chọn abstraction nào được tập trung trong adapter.

Một số lưu ý khi thiết kế facade:

- Tên breaker phải ổn định và đại diện cho phụ thuộc hoặc nhóm lời gọi có đặc tính vận hành tương đương.
- Không tạo breaker theo từng request, người dùng hoặc mã sản phẩm vì số lượng instance và dữ liệu thống kê sẽ tăng không kiểm soát.
- Không trả một publisher fallback có kiểu khác với publisher gốc.
- Quy định rõ lỗi nào được ghi nhận, lỗi nào được bỏ qua và fallback nào được phép sử dụng.
- Nếu facade có overload cho Mono và Flux, ghi rõ semantics của mỗi subscription để người dùng không hiểu nhầm một Flux là nhiều lời gọi độc lập.

Facade giúp thống nhất cách gọi trong mã ứng dụng, nhưng không làm biến mất khác biệt về hành vi giữa một publisher một kết quả và một stream nhiều phần tử.

## 5. Đặt fallback đúng vị trí trong chuỗi operator

Khi dùng Resilience4j Reactor operator trực tiếp, vị trí của onErrorResume ảnh hưởng đến dữ liệu mà circuit breaker ghi nhận.

Để breaker nhìn thấy lỗi từ publisher chính, sau đó mới chuyển lỗi sang fallback, hãy đặt operator circuit breaker trước onErrorResume:

    Flux<Product> products = webClient.get()
        .uri("/products")
        .retrieve()
        .bodyToFlux(Product.class)
        .transformDeferred(CircuitBreakerOperator.of(productBreaker))
        .onErrorResume(
            CallNotPermittedException.class,
            error -> Flux.empty()
        );

Trong ví dụ, nếu breaker OPEN, Resilience4j từ chối lời gọi bằng CallNotPermittedException. onErrorResume ở phía sau có thể chuyển trường hợp này thành Flux.empty(). Tùy nghiệp vụ, fallback cũng có thể trả về cache hoặc một sự kiện báo trạng thái suy giảm. Flux.empty() chỉ phù hợp khi việc không có dữ liệu được chấp nhận và không gây hiểu nhầm cho người dùng.

Nếu đặt onErrorResume trước circuit breaker:

    Flux<Product> products = webClient.get()
        .uri("/products")
        .retrieve()
        .bodyToFlux(Product.class)
        .onErrorResume(error -> Flux.empty())
        .transformDeferred(CircuitBreakerOperator.of(productBreaker));

Khi đó, lỗi nguồn đã được chuyển thành tín hiệu hoàn tất bình thường trước khi đến breaker. Breaker có thể ghi nhận subscription là thành công, làm tỷ lệ lỗi thấp hơn thực tế. Đây là lỗi cấu hình thường gặp khi fallback được đặt quá sớm trong chuỗi.

Trong thực tế, không nên bắt mọi Throwable rồi biến thành Flux.empty() nếu ứng dụng cần phân biệt lỗi mạng, lỗi máy chủ, lỗi giải mã dữ liệu và lỗi breaker từ chối. Hãy xử lý các loại lỗi theo chính sách nghiệp vụ. Với API Spring Cloud common cho Mono, hàm fallback được truyền trực tiếp vào run; với Resilience4j operator, fallback thường được ghép ở phía sau bằng các operator Reactor.

## 6. Một subscription là một lần gọi được bảo vệ

Một publisher lạnh thường thực hiện công việc khi được subscribe. Vì vậy, cùng một Mono hoặc Flux có thể được subscribe nhiều lần và mỗi subscription có thể tạo một lần gọi đến dịch vụ từ xa.

Ví dụ:

    Mono<Product> request = webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .transformDeferred(CircuitBreakerOperator.of(productBreaker));

    Mono<Product> first = request;
    Mono<Product> second = request;

Nếu cả first và second đều được subscribe, publisher lạnh có thể gửi hai HTTP request. Circuit breaker đánh giá từng lần thực thi theo semantics của operator. Không nên tạo nhiều subscription ngoài ý muốn, chẳng hạn vừa subscribe để ghi log vừa subscribe để trả dữ liệu. Hãy dùng các operator Reactor phù hợp để chia sẻ hoặc quan sát kết quả khi cần.

Với Flux, cần phân biệt hai trường hợp:

- **Flux đại diện cho một request hữu hạn:** ví dụ GET /products trả về một danh sách. Một subscription có thể được xem như một lần gọi phụ thuộc; breaker đánh giá kết quả khi publisher hoàn tất hoặc lỗi.
- **Flux là một stream dài hoặc vô hạn:** ví dụ kết nối nhận sự kiện liên tục. Toàn bộ subscription có thể kéo dài rất lâu và không có tín hiệu hoàn tất bình thường. Một breaker bọc toàn stream không tự động thống kê từng sự kiện như một lời gọi riêng.

Nếu stream vô hạn được bọc như một lần gọi, trạng thái thành công hoặc thời gian hoàn thành có thể không được ghi nhận theo cách phù hợp với mục tiêu thống kê. Hãy cân nhắc bảo vệ thao tác thiết lập kết nối, giám sát tín hiệu mất kết nối, timeout và cơ chế reconnect riêng. Không dùng circuit breaker như bộ đếm lỗi cho từng message trong một stream sống lâu.

Nếu mỗi phần tử đầu vào cần gọi một dịch vụ phụ thuộc riêng, hãy đặt breaker tại publisher của từng lời gọi đó. Ví dụ:

    Flux<EnrichedProduct> enriched = productIds.flatMap(id ->
        webClient.get()
            .uri("/products/{id}/details", id)
            .retrieve()
            .bodyToMono(ProductDetails.class)
            .transformDeferred(CircuitBreakerOperator.of(detailsBreaker))
            .map(details -> EnrichedProduct.from(id, details))
    );

Mỗi Mono bên trong flatMap đại diện cho một lời gọi riêng và được bảo vệ bởi breaker. Cần giới hạn concurrency của flatMap nếu nguồn có thể phát nhiều mã cùng lúc; circuit breaker không phải cơ chế giới hạn số lời gọi đồng thời. Bulkhead hoặc giới hạn concurrency có vai trò riêng.

## 7. Không gom Flux thành Mono chỉ để dùng API chung

Một cách có vẻ đơn giản để dùng ReactiveCircuitBreaker.run là chuyển Flux thành Mono bằng collectList():

    Mono<List<Product>> allProducts = webClient.get()
        .uri("/products")
        .retrieve()
        .bodyToFlux(Product.class)
        .collectList();

    return circuitBreakerFactory.create("product-list").run(
        allProducts,
        error -> Mono.just(List.of())
    );

Cách này phù hợp khi tập dữ liệu hữu hạn, có kích thước được kiểm soát và nghiệp vụ thực sự cần toàn bộ danh sách trước khi xử lý. Nhưng collectList() phải giữ các phần tử trong bộ nhớ cho đến khi Flux hoàn tất. Với danh sách lớn hoặc stream không kết thúc, nó có thể làm tăng bộ nhớ hoặc không bao giờ phát kết quả.

Không chuyển Flux thành Mono chỉ để né giới hạn API. Nếu cần streaming, giữ Flux và dùng CircuitBreakerOperator hoặc adapter ứng dụng hỗ trợ Flux. Nếu cần một kết quả tổng hợp, hãy chọn phép reduce, count hoặc collect phù hợp với yêu cầu dữ liệu và giới hạn kích thước đầu vào.

## 8. Cấu hình breaker và theo dõi lời gọi reactive

Cả reactive circuit breaker của Spring Cloud và Resilience4j operator đều dựa trên cấu hình của breaker tương ứng. Ví dụ cấu hình một instance cho luồng sản phẩm:

    resilience4j:
      circuitbreaker:
        instances:
          product-stream:
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 20
            minimumNumberOfCalls: 10
            failureRateThreshold: 50
            slowCallDurationThreshold: 1s
            slowCallRateThreshold: 60
            waitDurationInOpenState: 10s
            permittedNumberOfCallsInHalfOpenState: 3

Đây là cấu hình minh họa. Với COUNT_BASED, cửa sổ lưu kết quả của số lượng lời gọi gần nhất. minimumNumberOfCalls quy định số mẫu tối thiểu trước khi đánh giá tỷ lệ. failureRateThreshold và slowCallRateThreshold quyết định khi nào breaker mở theo tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm. waitDurationInOpenState xác định thời gian ở OPEN trước khi thử phục hồi; permittedNumberOfCallsInHalfOpenState giới hạn số lời gọi thử.

Chọn cấu hình theo đặc điểm publisher:

- Với request HTTP hữu hạn, đo thời gian phản hồi và tỷ lệ lỗi theo request.
- Với Flux trả về danh sách lớn, kiểm tra thời gian hoàn tất và giới hạn dữ liệu.
- Với stream dài, tách việc thiết lập kết nối khỏi việc xử lý từng message; dùng timeout, heartbeat, reconnect và metric riêng cho stream.
- Với nhiều lời gọi song song, cân nhắc bulkhead hoặc giới hạn concurrency ngoài circuit breaker.

Để quan sát, theo dõi trạng thái CLOSED, OPEN, HALF_OPEN, số lời gọi thành công/thất bại/bị từ chối, tỷ lệ lời gọi chậm và thời gian phản hồi. Với reactive flow, cũng cần quan sát số subscription, số stream đang hoạt động, số lần reconnect, lỗi khi giải mã dữ liệu và số lần fallback được dùng. Các chỉ số này giúp phân biệt breaker đang ngăn lời gọi đến phụ thuộc lỗi với trường hợp stream gặp vấn đề ở tầng xử lý dữ liệu.

Spring Boot Actuator và Micrometer có thể được dùng để xuất metric của ứng dụng và Resilience4j khi đã cấu hình tích hợp phù hợp. Tên metric và endpoint cụ thể phụ thuộc phiên bản, registry và cấu hình expose. Hãy kiểm tra các metric thực tế của ứng dụng, bảo vệ endpoint quản trị và tránh đưa dữ liệu nhạy cảm như token hoặc payload người dùng vào tag.

## 9. Bài thực hành: bảo vệ Mono và Flux

Xây dựng một reactive gateway có hai chức năng: tra cứu chi tiết một sản phẩm và đọc danh sách sản phẩm từ catalog-service.

**Phần A — Mono qua API chung**

1. Tạo WebClient trỏ đến catalog-service.
2. Viết phương thức findById trả về Mono<Product>.
3. Inject ReactiveCircuitBreakerFactory và tạo breaker tên product-detail.
4. Bọc Mono bằng run và cung cấp fallback thể hiện dữ liệu không xác định hoặc lỗi nghiệp vụ phù hợp.
5. Làm dịch vụ phụ thuộc trả lỗi và phản hồi chậm để quan sát fallback cùng trạng thái breaker.

**Phần B — Flux qua operator**

1. Viết phương thức list trả về Flux<Product>.
2. Lấy CircuitBreaker có tên product-stream từ CircuitBreakerRegistry.
3. Trang trí Flux bằng transformDeferred(CircuitBreakerOperator.of(...)).
4. Đặt onErrorResume sau operator và chỉ xử lý những lỗi được nghiệp vụ cho phép.
5. Kiểm tra rằng publisher vẫn phát dữ liệu theo dạng Flux và lỗi của nguồn được breaker ghi nhận.

**Phần C — Kiểm tra subscription và stream dài**

1. Subscribe một publisher lạnh hai lần và quan sát số request thực tế.
2. Thử một Flux hữu hạn và một stream mô phỏng kéo dài.
3. Xác định thời điểm publisher hoàn tất, phát sinh lỗi hoặc bị hủy.
4. Đánh giá xem một breaker bao quanh toàn stream có cung cấp số liệu phù hợp không.
5. Nếu từng phần tử cần một lời gọi riêng, chuyển breaker vào publisher của lời gọi trong flatMap và giới hạn concurrency phù hợp.

Khi hoàn thành, bạn cần giải thích được vì sao Mono có thể dùng trực tiếp ReactiveCircuitBreaker.run, cách dùng Resilience4j Reactor operator để bảo vệ Flux, vị trí fallback ảnh hưởng đến thống kê ra sao và một subscription đại diện cho thao tác nào. Những hiểu biết này giúp bảo vệ lời gọi reactive mà vẫn giữ đúng semantics của publisher và dữ liệu vận hành.

