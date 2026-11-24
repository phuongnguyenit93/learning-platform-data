# Ánh xạ factory.create(id, groupName) với cấu hình nhóm

## Mục tiêu của bài học

Trong một ứng dụng Spring Cloud CircuitBreaker, nhiều lời gọi có thể cùng truy cập một dịch vụ phụ thuộc. Ví dụ, order-service có các thao tác đọc tồn kho, giữ hàng và giải phóng hàng; cả ba thao tác đều gọi inventory-service nhưng có thể cần timeout và ngưỡng circuit breaker khác nhau.

API factory cung cấp hai tham số để mô tả ranh giới cấu hình:

- id định danh một thao tác hoặc lời gọi cụ thể, chẳng hạn inventory-read.
- groupName xác định nhóm dịch vụ mà thao tác thuộc về, chẳng hạn inventory.

Việc hiểu cách ánh xạ hai giá trị này với cấu hình Resilience4j giúp dùng chung chính sách cho một nhóm thao tác, đồng thời cho phép một thao tác có cấu hình riêng. Sau bài học, bạn có thể:

- Phân biệt id và groupName trong factory.create(id, groupName).
- Ánh xạ cấu hình theo thứ tự thao tác, nhóm dịch vụ và mặc định toàn cục.
- Khai báo cấu hình nhóm trong resilience4j.circuitbreaker.configs và resilience4j.timelimiter.configs.
- Dùng cấu hình riêng trong instances để điều chỉnh một thao tác.
- Hiểu rằng CircuitBreaker và TimeLimiter được phân giải cấu hình riêng.
- Kiểm tra vì sao một lời gọi đang dùng cấu hình nhóm hoặc cấu hình mặc định.

## 1. Hai tham số mô tả hai cấp cấu hình

Spring Cloud CircuitBreaker cung cấp factory để tạo circuit breaker theo tên. Với Resilience4j, hai cách gọi phổ biến là:

    CircuitBreaker breaker = factory.create("inventory-read");
    CircuitBreaker groupedBreaker = factory.create("inventory-read", "inventory");

Trong ví dụ thứ hai:

- inventory-read là id. Nó đại diện cho thao tác hoặc phương thức đang được bảo vệ.
- inventory là groupName. Nó đại diện cho nhóm dịch vụ hoặc nhóm thao tác có chung chính sách.

Có thể hình dung cấu trúc như sau:

    order-service
      |
      +-- inventory-read     --+
      +-- inventory-reserve   --+--> groupName: inventory
      +-- inventory-release  --+

Các thao tác có thể cùng thuộc nhóm inventory để dùng chung cấu hình nhóm. Tuy nhiên, id vẫn phân biệt từng circuit breaker. Mỗi id có thể có trạng thái CLOSED, OPEN hoặc HALF_OPEN và số liệu riêng. groupName giúp chọn cấu hình; nó không gộp trạng thái của nhiều breaker thành một breaker duy nhất.

Cách đặt tên nên ổn định và phản ánh trách nhiệm:

| Giá trị | Ví dụ | Vai trò |
| --- | --- | --- |
| id | inventory-read | Định danh một lời gọi cụ thể để cấu hình và theo dõi riêng. |
| groupName | inventory | Gom các lời gọi cùng phụ thuộc hoặc cùng chính sách vận hành. |
| id khác | inventory-reserve | Một breaker riêng có thể dùng chung chính sách nhóm inventory. |
| groupName khác | pricing | Nhóm cấu hình cho các lời gọi đến pricing-service. |

Không tạo id theo từng request, user hoặc mã sản phẩm. Nếu tên thay đổi liên tục, ứng dụng có thể tạo quá nhiều breaker và dữ liệu thống kê bị chia nhỏ. Nên đặt id theo thao tác nghiệp vụ có vòng đời ổn định.

## 2. Thứ tự phân giải cấu hình

Spring Cloud CircuitBreaker với Resilience4j hỗ trợ ba cấp cấu hình, theo thứ tự ưu tiên từ cao xuống thấp:

1. **Method hoặc operation (id):** cấu hình riêng cho thao tác cụ thể.
2. **Service group (groupName):** cấu hình dùng chung cho nhóm dịch vụ hoặc các thao tác cùng loại.
3. **Global default:** cấu hình mặc định cho các breaker không có cấu hình riêng hoặc cấu hình nhóm phù hợp.

Quy tắc này được áp dụng riêng cho CircuitBreaker và TimeLimiter. Vì vậy, một thao tác có thể lấy cấu hình circuit breaker từ cấp id, nhưng lấy cấu hình time limiter từ cấp groupName nếu không có cấu hình time limiter riêng cho id.

Ví dụ:

| Lời gọi factory | Cấu hình CircuitBreaker | Cấu hình TimeLimiter |
| --- | --- | --- |
| create("backendA") | instances.backendA nếu có; nếu không thì dùng mặc định phù hợp. | instances.backendA nếu có; nếu không thì dùng mặc định phù hợp. |
| create("backendA", "groupA") | Ưu tiên cấu hình backendA; nếu không có thì xét groupA; cuối cùng là mặc định. | Ưu tiên cấu hình backendA; nếu không có thì xét groupA; cuối cùng là mặc định. |
| create("backendC", "groupC") khi chỉ có cấu hình nhóm cho TimeLimiter | Dùng cấu hình CircuitBreaker mặc định. | Dùng cấu hình TimeLimiter của groupC. |

Ví dụ cuối cho thấy groupName không bắt buộc phải có cấu hình cho cả hai thành phần. Nếu groupC chỉ được khai báo trong resilience4j.timelimiter.configs, TimeLimiter có thể dùng cấu hình nhóm đó trong khi CircuitBreaker vẫn dùng mặc định toàn cục.

Khi gọi create(id) không truyền groupName, factory sử dụng id làm tên nhóm trong quá trình phân giải. Nếu không có cấu hình phù hợp cho id, kết quả sẽ rơi về mặc định toàn cục. Khi cần gom nhiều id dưới một nhóm chung, hãy truyền groupName rõ ràng.

## 3. Khai báo cấu hình nhóm trong application.yml

Resilience4j phân biệt cấu hình dùng chung trong configs và cấu hình theo instance trong instances. Có thể khai báo một nhóm inventory cùng nhóm mặc định như sau:

    resilience4j:
      circuitbreaker:
        configs:
          default:
            registerHealthIndicator: true
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 50
            minimumNumberOfCalls: 10
            failureRateThreshold: 50
          inventory:
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 100
            minimumNumberOfCalls: 20
            failureRateThreshold: 40
            slowCallDurationThreshold: 800ms
            slowCallRateThreshold: 60
        instances:
          inventory-read:
            baseConfig: inventory
            minimumNumberOfCalls: 8

      timelimiter:
        configs:
          default:
            timeoutDuration: 5s
            cancelRunningFuture: true
          inventory:
            timeoutDuration: 2s
            cancelRunningFuture: true
        instances:
          inventory-read:
            baseConfig: inventory
            timeoutDuration: 700ms

Ý nghĩa của cấu hình:

- configs.default là chính sách mặc định toàn cục.
- configs.inventory là chính sách nhóm cho các lời gọi thuộc inventory.
- instances.inventory-read là cấu hình riêng cho thao tác inventory-read.
- baseConfig: inventory cho biết instance inventory-read kế thừa cấu hình nhóm inventory, sau đó áp dụng các giá trị riêng được khai báo trong instance.
- Cấu hình CircuitBreaker và TimeLimiter được đặt trong hai nhánh riêng; không trộn timeout vào circuitbreaker.

Với cấu hình trên, inventory-read kế thừa cửa sổ 100 lời gọi, failure rate threshold 40 và timeout 2 giây từ nhóm inventory, sau đó ghi đè minimumNumberOfCalls thành 8 và timeout thành 700 mili giây. Một thao tác khác như inventory-list nếu không có cấu hình riêng sẽ dùng trực tiếp cấu hình nhóm inventory khi được tạo với groupName tương ứng.

Cấu hình nhóm không phải là cấu hình bắt buộc cho mọi dịch vụ. Nếu một nhóm không có trong configs, factory tiếp tục dùng mặc định toàn cục cho thành phần đó. Nếu một instance không có trong instances, factory có thể phân giải theo groupName.

## 4. Ánh xạ cấu hình bằng factory.create(id, groupName)

Giả sử order-service cần đọc tồn kho và giữ hàng. Cả hai thao tác thuộc nhóm inventory nhưng có id riêng:

    import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
    import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
    import org.springframework.stereotype.Service;
    import org.springframework.web.client.RestClient;

    @Service
    public class InventoryGateway {

        private final RestClient inventoryClient;
        private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

        public InventoryGateway(
                RestClient inventoryClient,
                CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
            this.inventoryClient = inventoryClient;
            this.circuitBreakerFactory = circuitBreakerFactory;
        }

        public InventoryResponse read(String sku) {
            CircuitBreaker breaker =
                circuitBreakerFactory.create("inventory-read", "inventory");

            return breaker.run(
                () -> inventoryClient.get()
                    .uri("/inventory/{sku}", sku)
                    .retrieve()
                    .body(InventoryResponse.class),
                error -> InventoryResponse.unknown(sku)
            );
        }

        public ReservationResponse reserve(String sku) {
            CircuitBreaker breaker =
                circuitBreakerFactory.create("inventory-reserve", "inventory");

            return breaker.run(
                () -> inventoryClient.post()
                    .uri("/inventory/{sku}/reserve", sku)
                    .retrieve()
                    .body(ReservationResponse.class),
                error -> ReservationResponse.pending(sku)
            );
        }
    }

Hai lời gọi cùng dùng groupName inventory nên có thể chia sẻ chính sách cấu hình nhóm. Nhưng id inventory-read và inventory-reserve khác nhau, vì vậy trạng thái và thống kê breaker được tách riêng. Cách này giúp một thao tác đọc lỗi không nhất thiết làm breaker của thao tác giữ hàng mở theo.

InventoryResponse.unknown và ReservationResponse.pending là các phương thức do ứng dụng định nghĩa. Fallback phải phản ánh đúng ý nghĩa nghiệp vụ. Đặc biệt, không nên trả về trạng thái đã giữ hàng thành công nếu không xác nhận được kết quả từ dịch vụ phụ thuộc.

## 5. Dùng groupName với lời gọi reactive

Reactive factory cũng hỗ trợ create(id, groupName). Với WebClient, lời gọi trả về Mono có thể dùng cùng cách ánh xạ cấu hình:

    import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
    import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
    import org.springframework.stereotype.Service;
    import org.springframework.web.reactive.function.client.WebClient;
    import reactor.core.publisher.Mono;

    @Service
    public class ReactiveInventoryGateway {

        private final WebClient inventoryClient;
        private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;

        public ReactiveInventoryGateway(
                WebClient inventoryClient,
                ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
            this.inventoryClient = inventoryClient;
            this.circuitBreakerFactory = circuitBreakerFactory;
        }

        public Mono<InventoryResponse> read(String sku) {
            ReactiveCircuitBreaker breaker =
                circuitBreakerFactory.create("inventory-read", "inventory");

            Mono<InventoryResponse> request = inventoryClient.get()
                .uri("/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(InventoryResponse.class);

            return breaker.run(
                request,
                error -> Mono.just(InventoryResponse.unknown(sku))
            );
        }
    }

Reactive factory dùng cùng nguyên tắc phân giải id và groupName. Publisher vẫn được xử lý theo mô hình reactive; không cần chuyển Mono thành Future chỉ để chọn cấu hình nhóm. Khi ứng dụng cần bảo vệ Flux, cần kiểm tra abstraction và implementation đang dùng; API common reactive tập trung vào Mono, còn Resilience4j Reactor operator có thể được dùng để trang trí Flux.

GroupName không thay đổi kiểu dữ liệu trả về và cũng không quyết định fallback nào được chạy. Fallback vẫn do lời gọi cung cấp hoặc do cấu hình/customizer của ứng dụng quyết định.

## 6. Phân biệt cấu hình CircuitBreaker và TimeLimiter

CircuitBreaker và TimeLimiter có mục đích khác nhau:

- CircuitBreaker đánh giá kết quả lời gọi, tỷ lệ lỗi và lời gọi chậm để chuyển giữa CLOSED, OPEN và HALF_OPEN.
- TimeLimiter giới hạn thời gian thực thi mà ứng dụng chờ đợi đối với lời gọi được hỗ trợ.

Cả hai có thể nhận cấu hình theo id, groupName và mặc định, nhưng dữ liệu cấu hình được khai báo trong các nhánh riêng:

| Thành phần | Cấu hình nhóm | Cấu hình instance |
| --- | --- | --- |
| CircuitBreaker | resilience4j.circuitbreaker.configs.inventory | resilience4j.circuitbreaker.instances.inventory-read |
| TimeLimiter | resilience4j.timelimiter.configs.inventory | resilience4j.timelimiter.instances.inventory-read |

Ví dụ, nếu chỉ khai báo:

    resilience4j:
      circuitbreaker:
        configs:
          default:
            slidingWindowSize: 50
            failureRateThreshold: 50
      timelimiter:
        configs:
          default:
            timeoutDuration: 5s
          inventory:
            timeoutDuration: 2s

Khi gọi factory.create("inventory-read", "inventory"), CircuitBreaker không tìm thấy cấu hình instance inventory-read hoặc group inventory trong registry nên dùng cấu hình mặc định. TimeLimiter tìm thấy cấu hình group inventory nên dùng timeout 2 giây.

Đây là lý do không nên suy luận rằng truyền groupName luôn thay đổi cả hai thành phần giống nhau. Hãy kiểm tra từng nhánh cấu hình và kết quả phân giải tương ứng.

## 7. Kết hợp cấu hình properties và Java Customizer

Spring Cloud CircuitBreaker cho phép cấu hình qua application.yml và qua Java Customizer. Properties có độ ưu tiên cao hơn cấu hình Customizer. Nếu một giá trị trong file cấu hình khác với giá trị được tạo bằng Java, hãy kiểm tra xem properties có đang ghi đè kết quả hay không.

Ví dụ cấu hình mặc định bằng Java:

    @Bean
    Customizer<Resilience4JCircuitBreakerFactory> defaultCustomizer() {
        return factory -> factory.configureDefault(id ->
            new Resilience4JConfigBuilder(id)
                .circuitBreakerConfig(CircuitBreakerConfig.ofDefaults())
                .timeLimiterConfig(
                    TimeLimiterConfig.custom()
                        .timeoutDuration(Duration.ofSeconds(4))
                        .build()
                )
                .build()
        );
    }

Customizer mặc định hữu ích khi muốn định nghĩa chính sách chung trong mã Java. Tuy nhiên, với các nhóm có chính sách rõ ràng như inventory và pricing, cấu hình properties thường dễ đọc, dễ so sánh giữa môi trường và dễ vận hành hơn.

Không khai báo cùng một chính sách ở nhiều nơi nếu không cần thiết. Khi có cả properties và Customizer, ghi rõ nơi nào là nguồn cấu hình có thẩm quyền. Nếu không, người bảo trì có thể sửa Java nhưng không thấy hành vi thay đổi vì cấu hình properties có ưu tiên cao hơn.

## 8. Kiểm tra ánh xạ bằng các trường hợp cụ thể

Hãy kiểm tra theo từng tình huống thay vì chỉ nhìn tên cấu hình:

| Tình huống | id | groupName | Kết quả mong đợi |
| --- | --- | --- | --- |
| Có cấu hình instance | inventory-read | inventory | Dùng cấu hình riêng của inventory-read; nếu instance có baseConfig thì kế thừa nhóm/default được chỉ định. |
| Không có instance, có group | inventory-list | inventory | Dùng cấu hình nhóm inventory. |
| Không có instance và group | pricing-quote | pricing | Dùng global default cho thành phần không có cấu hình phù hợp. |
| Chỉ TimeLimiter có cấu hình nhóm | inventory-read | inventory | CircuitBreaker có thể dùng global default trong khi TimeLimiter dùng nhóm inventory. |
| Có instance và cấu hình nhóm khác nhau | inventory-read | inventory | Cấu hình instance được ưu tiên; cấu hình nhóm không tự ghi đè instance. |

Khi ứng dụng không dùng timeout như dự kiến, kiểm tra lần lượt:

1. Tên id truyền vào factory có trùng với key trong instances không?
2. groupName có trùng với key trong configs không?
3. Cấu hình có nằm đúng nhánh circuitbreaker hoặc timelimiter không?
4. Instance có baseConfig trỏ đến một nhóm khác không?
5. Có Java Customizer hoặc properties ở môi trường khác đang ảnh hưởng không?
6. TimeLimiter có bị tắt theo cấu hình toàn cục, group hoặc instance không?

Có thể bật log cấu hình ở mức phù hợp và kiểm tra metric của breaker sau khi ứng dụng khởi động. Không đưa dữ liệu nhạy cảm vào log chỉ để xác minh tên cấu hình.

## 9. Bài thực hành: tạo hai thao tác trong cùng nhóm

Tạo hai phương thức trong inventory gateway: đọc thông tin tồn kho và giữ hàng. Dùng groupName inventory cho cả hai, nhưng đặt id riêng cho từng thao tác.

1. Khai báo configs.default với sliding window và timeout mặc định.
2. Khai báo configs.inventory với sliding window và timeout phù hợp cho inventory-service.
3. Tạo phương thức read dùng factory.create("inventory-read", "inventory").
4. Tạo phương thức reserve dùng factory.create("inventory-reserve", "inventory").
5. Quan sát rằng cả hai dùng chính sách nhóm nếu không có cấu hình instance riêng.
6. Thêm instances.inventory-read với baseConfig: inventory và thay minimumNumberOfCalls.
7. Khởi động lại ứng dụng, kiểm tra read dùng cấu hình riêng còn reserve tiếp tục dùng cấu hình nhóm.
8. Chỉ khai báo cấu hình TimeLimiter cho một nhóm thử nghiệm khác để quan sát trường hợp CircuitBreaker và TimeLimiter nhận cấp cấu hình khác nhau.

Kết quả cần đạt là bạn có thể giải thích id là tên của thao tác được bảo vệ, groupName là cấp cấu hình dịch vụ, cấu hình instance được ưu tiên hơn cấu hình nhóm, và mặc định toàn cục được dùng khi không tìm thấy cấu hình cụ thể. Bạn cũng cần xác định riêng cấu hình của CircuitBreaker và TimeLimiter thay vì giả định hai thành phần luôn nhận cùng một mức cấu hình.

## Tài liệu tham khảo

- Spring Cloud CircuitBreaker — Circuit Breaker Properties Configuration: https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j/circuit-breaker-properties-configuration.html
- Spring Cloud CircuitBreaker — Resilience4J implementation: https://docs.spring.io/spring-cloud-circuitbreaker/docs/current/reference/html/spring-cloud-circuitbreaker-resilience4j.html

