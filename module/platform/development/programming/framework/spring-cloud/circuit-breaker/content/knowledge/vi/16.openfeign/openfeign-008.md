# Kiểm chứng ngắt mạch khi dùng Service Discovery và LoadBalancer

## Mục tiêu của bài học

Trong hệ thống microservices, OpenFeign thường gọi dịch vụ bằng service ID thay vì địa chỉ IP cố định. Service Discovery cung cấp danh sách instance đang được đăng ký; Spring Cloud LoadBalancer chọn một instance cho mỗi lần gọi. Circuit breaker bảo vệ thao tác gọi đó khi dịch vụ lỗi hoặc phản hồi quá chậm.

Ba cơ chế có liên quan nhưng không thay thế nhau. Discovery tìm instance, LoadBalancer chọn đích, còn circuit breaker quyết định có cho phép một lời gọi logic mới đi qua hay không dựa trên kết quả gần đây. Để kiểm chứng đúng, cần biết breaker đang bao quanh lời gọi Feign nào, LoadBalancer đã chọn instance nào và lỗi xuất hiện ở tầng nào.

Sau bài học, bạn có thể:

- Cấu hình OpenFeign gọi dịch vụ qua service ID và Spring Cloud LoadBalancer.
- Bật tích hợp Spring Cloud CircuitBreaker cho Feign client.
- Giải thích đường đi của một request từ Feign qua LoadBalancer đến instance được chọn.
- Phân biệt breaker theo client/method với trạng thái sức khỏe của từng instance.
- Kiểm tra hành vi khi registry không có instance, một instance lỗi hoặc toàn bộ dịch vụ chậm.
- Dùng fallback hoặc FallbackFactory để phản hồi có kiểm soát.
- Đọc metric và log để xác định lỗi đến từ discovery, load balancing, HTTP hay circuit breaker.
- Kiểm tra ảnh hưởng của retry, timeout và cấu hình URL cố định.

## 1. Ba trách nhiệm trong một lời gọi OpenFeign

Giả sử order-service cần lấy tồn kho từ inventory-service. Ứng dụng khai báo Feign client bằng tên dịch vụ:

    @FeignClient(name = "inventory-service")
    public interface InventoryClient {

        @GetMapping("/inventory/{sku}")
        InventoryResponse find(@PathVariable("sku") String sku);
    }

Khi không khai báo URL cố định, tên inventory-service được dùng làm service ID. Đường đi điển hình:

    order-service
        |
        v
    InventoryClient (OpenFeign)
        |
        v
    CircuitBreaker (nếu được bật)
        |
        v
    Feign request handler
        |
        v
    Spring Cloud LoadBalancer
        |
        +---- chọn instance A ----> inventory-service
        |
        +---- hoặc instance B ---> inventory-service

Mỗi thành phần có trách nhiệm riêng:

| Thành phần | Trách nhiệm | Điều nó không tự giải quyết |
| --- | --- | --- |
| Service Discovery | Đăng ký và cung cấp danh sách instance theo service ID. | Không quyết định một lời gọi nghiệp vụ có nên tiếp tục sau nhiều lỗi hay không. |
| Spring Cloud LoadBalancer | Chọn một instance từ danh sách có sẵn cho lời gọi. | Không tự tạo circuit breaker theo kết quả nhiều lần gọi Feign. |
| CircuitBreaker | Theo dõi kết quả lời gọi được bảo vệ và chặn lời gọi mới khi breaker OPEN. | Không tự cập nhật registry hoặc tự loại một instance lỗi khỏi danh sách discovery. |
| OpenFeign | Tạo lời gọi HTTP theo interface khai báo. | Không thay thế discovery, load balancing hoặc chính sách phục hồi. |

Circuit breaker của Feign bảo vệ một ranh giới lời gọi logic. LoadBalancer chọn instance ở phía dưới ranh giới đó. Vì vậy, một breaker theo client/method có thể quan sát kết quả từ nhiều instance khác nhau.

## 2. Khai báo các dependency cần thiết

Một ứng dụng dùng OpenFeign, Service Discovery, LoadBalancer và Resilience4j CircuitBreaker cần các thành phần tương ứng. Ví dụ Maven:

    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-openfeign</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-loadbalancer</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
        </dependency>

        <!-- Thêm discovery client phù hợp, ví dụ Eureka, Consul hoặc Kubernetes. -->
    </dependencies>

Các phiên bản nên được quản lý bởi Spring Cloud BOM tương thích với Spring Boot của dự án. Discovery client cụ thể phụ thuộc nền tảng registry mà hệ thống sử dụng. Nếu LoadBalancer hoặc CircuitBreaker starter đã được đưa vào classpath thông qua dependency khác, kiểm tra dependency tree trước khi thêm trùng.

Bật quét Feign client trong ứng dụng:

    @SpringBootApplication
    @EnableFeignClients
    public class OrderApplication {

        public static void main(String[] args) {
            SpringApplication.run(OrderApplication.class, args);
        }
    }

Ứng dụng cũng cần cấu hình discovery client để đăng ký hoặc tra cứu inventory-service. Tên service ID trong registry phải khớp với name của @FeignClient.

## 3. Bật CircuitBreaker cho OpenFeign

Spring Cloud OpenFeign hỗ trợ tích hợp Spring Cloud CircuitBreaker. Với Resilience4j, starter implementation phải có trên classpath và tính năng circuit breaker của OpenFeign phải được bật:

    spring:
      cloud:
        openfeign:
          circuitbreaker:
            enabled: true

Khi tính năng này được bật, các phương thức Feign client được tạo qua cơ chế tích hợp sẽ được thực thi trong circuit breaker. Nếu không bật property, việc chỉ có OpenFeign và Resilience4j trên classpath không đồng nghĩa mọi Feign method đã được bảo vệ.

Ví dụ client có fallback factory:

    @FeignClient(
        name = "inventory-service",
        contextId = "inventoryReadClient",
        fallbackFactory = InventoryFallbackFactory.class
    )
    public interface InventoryClient {

        @GetMapping("/inventory/{sku}")
        InventoryResponse find(@PathVariable("sku") String sku);
    }

contextId giúp phân biệt cấu hình client khi một ứng dụng có nhiều Feign client cùng gọi một service ID. name vẫn là service ID được dùng để tìm dịch vụ qua LoadBalancer.

Không khai báo thuộc tính url nếu mục tiêu là để LoadBalancer chọn instance theo service ID. Khi URL cố định được cấu hình trực tiếp trên @FeignClient hoặc cấu hình client tương ứng, đường gọi sẽ dùng địa chỉ đó và bỏ qua cơ chế lựa chọn instance theo service ID. Circuit breaker vẫn có thể bảo vệ lời gọi Feign, nhưng bài kiểm thử không còn xác minh được discovery và LoadBalancer.

## 4. Hiểu breaker đang bảo vệ phạm vi nào

Khi Feign CircuitBreaker được bật, lời gọi phương thức Feign được bọc bởi circuit breaker. Trong một request, phần thực thi bên trong có thể bao gồm việc lấy instance từ LoadBalancer, tạo HTTP request và nhận response.

Ví dụ, order-service gọi:

    inventoryClient.find("SKU-42");

LoadBalancer có thể chọn instance A ở lần đầu và instance B ở lần tiếp theo. Nếu cùng một breaker name được dùng cho phương thức find, kết quả từ những instance được chọn sẽ đóng góp vào thống kê của breaker đó.

Điều này tạo ra hai điểm cần hiểu:

- Breaker theo client/method thường đánh giá kết quả tổng hợp của các lần gọi logic, không mặc định tạo một breaker riêng cho từng IP hoặc từng instance.
- Nếu một instance lỗi nhưng các instance còn lại khỏe mạnh, các lần gọi thất bại từ instance lỗi vẫn có thể ảnh hưởng đến thống kê chung của breaker.

Circuit breaker không tự đánh dấu instance A là unhealthy trong Service Registry. Việc đăng ký, hủy đăng ký, health check và lọc instance thuộc trách nhiệm của discovery client hoặc cấu hình LoadBalancer. Nếu cần loại một instance lỗi khỏi lựa chọn, phải kiểm tra cơ chế health check và trạng thái instance của nền tảng discovery.

Không nên diễn giải trạng thái OPEN của breaker inventory-read thành kết luận rằng mọi instance inventory-service đều hỏng. Nó chỉ cho biết lời gọi được bảo vệ đã đạt điều kiện mở breaker theo số liệu và ngưỡng cấu hình.

## 5. Cấu hình Resilience4j cho lời gọi Feign

Tên breaker được tạo theo quy tắc đặt tên của Spring Cloud OpenFeign và phiên bản đang dùng. Không nên đoán tên từ service ID rồi giả định cấu hình chắc chắn đã được áp dụng. Hãy kiểm tra tên thực tế trong log, metric hoặc cấu hình CircuitBreakerNameResolver của ứng dụng.

Khi đã xác định đúng breaker name, có thể cấu hình instance Resilience4j:

    resilience4j:
      circuitbreaker:
        instances:
          <feign-breaker-name>:
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 20
            minimumNumberOfCalls: 10
            failureRateThreshold: 50
            slowCallDurationThreshold: 1500ms
            slowCallRateThreshold: 60
            waitDurationInOpenState: 10s
            permittedNumberOfCallsInHalfOpenState: 3

Các giá trị trong ví dụ chỉ minh họa. Hãy chọn cửa sổ, số mẫu tối thiểu, tỷ lệ lỗi và ngưỡng lời gọi chậm dựa trên lưu lượng cũng như ngân sách thời gian của inventory-service.

Có thể cấu hình timeout của Feign client riêng:

    spring:
      cloud:
        openfeign:
          client:
            config:
              inventoryReadClient:
                connectTimeout: 500
                readTimeout: 1200

Cấu hình client cụ thể cần khớp với tên cấu hình Feign mà phiên bản dự án sử dụng. Trong dự án thực tế, kiểm tra tài liệu phiên bản và cấu hình đã được bind để xác nhận timeout đang áp dụng cho đúng client.

Timeout của Feign giới hạn thời gian chờ ở tầng HTTP client. slowCallDurationThreshold của CircuitBreaker chỉ phân loại lời gọi chậm trong thống kê. Hai cấu hình này có vai trò khác nhau: một cái giới hạn thời gian của request, cái còn lại giúp breaker đánh giá tình trạng phụ thuộc.

## 6. Dùng FallbackFactory để nhận biết nguyên nhân

FallbackFactory cho phép tạo fallback dựa trên Throwable gây ra lỗi. Điều này hữu ích khi cần phân biệt breaker OPEN, không tìm thấy instance, timeout hoặc lỗi HTTP.

Ví dụ:

    @Component
    public class InventoryFallbackFactory
            implements FallbackFactory<InventoryClient> {

        @Override
        public InventoryClient create(Throwable cause) {
            return sku -> {
                if (hasCause(cause, CallNotPermittedException.class)) {
                    return InventoryResponse.unavailable(sku);
                }

                if (isNoInstanceFailure(cause)) {
                    return InventoryResponse.unavailable(sku);
                }

                if (isTimeoutFailure(cause)) {
                    return InventoryResponse.unknown(sku);
                }

                return InventoryResponse.unknown(sku);
            };
        }

        private boolean hasCause(Throwable error, Class<?> type) {
            Throwable current = error;
            while (current != null) {
                if (type.isInstance(current)) {
                    return true;
                }
                current = current.getCause();
            }
            return false;
        }

        private boolean isNoInstanceFailure(Throwable error) {
            // Kiểm tra exception cụ thể do discovery/LoadBalancer của dự án phát ra.
            return false;
        }

        private boolean isTimeoutFailure(Throwable error) {
            // Phân loại exception timeout theo HTTP client đang sử dụng.
            return false;
        }
    }

Các phương thức isNoInstanceFailure và isTimeoutFailure là điểm mở rộng cần triển khai theo exception thực tế của hệ thống. Không nên phụ thuộc vào một chuỗi message lỗi vì message có thể thay đổi theo phiên bản hoặc implementation.

InventoryResponse.unavailable và unknown là phương thức do ứng dụng định nghĩa. Fallback không nên trả về tồn kho bằng 0 hoặc khẳng định hết hàng khi không truy vấn được dịch vụ. Hãy thể hiện rõ dữ liệu không xác định hoặc nguồn dịch vụ hiện không khả dụng.

FallbackFactory cũng cần được đặt trong phạm vi component scan. Nếu dùng fallback class trực tiếp thay cho factory, cần bảo đảm nó triển khai đúng interface Feign client và có thể được Spring tạo bean.

## 7. Kiểm chứng Service Discovery và LoadBalancer

Để kiểm chứng đường đi thực tế, hãy bắt đầu với ít nhất hai instance inventory-service có thể phân biệt được qua log hoặc response. Mỗi instance có thể trả về một trường instanceId trong môi trường thử nghiệm.

Ví dụ cấu hình SimpleDiscoveryClient trong môi trường test:

    spring:
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: http://localhost:8081
                  - uri: http://localhost:8082

Đây là cách tạo danh sách instance tĩnh cho kiểm thử. Trong môi trường thật, registry như Eureka, Consul hoặc Kubernetes cung cấp danh sách instance theo cơ chế tương ứng.

Thực hiện lần lượt:

1. Khởi động hai instance inventory-service ở cổng 8081 và 8082.
2. Khởi động order-service với OpenFeign, LoadBalancer và CircuitBreaker đã bật.
3. Gọi inventoryClient.find nhiều lần và quan sát instanceId hoặc access log ở hai instance.
4. Xác nhận cả hai instance có thể được chọn theo chiến lược LoadBalancer hiện hành.
5. Dừng một instance hoặc làm instance đó trả lỗi có kiểm soát.
6. Tiếp tục gọi từ order-service và ghi lại instance được chọn, exception và trạng thái breaker.
7. Dừng toàn bộ instance hoặc làm registry trả danh sách rỗng.
8. Quan sát lỗi không tìm thấy instance, fallback và metric breaker.
9. Khởi động lại các instance, theo dõi quá trình đăng ký lại và trạng thái phục hồi.

Không giả định LoadBalancer luôn loại ngay một instance chỉ vì một request thất bại. Việc loại instance phụ thuộc health check, registry và cấu hình cụ thể. Nếu instance lỗi vẫn được quảng bá, LoadBalancer có thể tiếp tục chọn nó.

## 8. Phân biệt lỗi của một instance và lỗi của cả service

Hãy kiểm tra ba tình huống riêng:

| Tình huống | Discovery/LoadBalancer | CircuitBreaker |
| --- | --- | --- |
| Một instance lỗi, instance khác khỏe | Có thể vẫn chọn cả instance lỗi nếu registry chưa loại nó. | Ghi nhận kết quả lời gọi Feign; breaker có thể tiếp tục CLOSED nếu tỷ lệ lỗi chưa vượt ngưỡng. |
| Tất cả instance không khả dụng hoặc không được đăng ký | Không có đích phù hợp; lời gọi có thể thất bại trước khi gửi HTTP request. | Lỗi từ quá trình gọi có thể được ghi nhận theo cấu hình breaker và dẫn đến OPEN. |
| Service phản hồi chậm trên nhiều instance | LoadBalancer vẫn có thể chọn instance; discovery không nhất thiết nhận biết độ trễ request. | Slow call rate có thể tăng và breaker có thể mở sau khi đủ mẫu. |

Nếu chỉ một instance lỗi nhưng breaker mở, các lời gọi đến instance khỏe cũng có thể bị chặn trong thời gian OPEN vì chúng dùng cùng breaker name. Khi đó, cần xử lý nguyên nhân ở tầng instance health và cân nhắc ranh giới breaker phù hợp.

Nếu muốn circuit breaker riêng cho từng instance, cần một thiết kế có định danh instance ở thời điểm chọn đích và tích hợp có chủ đích với LoadBalancer. Cấu hình Feign CircuitBreaker mặc định không nên được xem là tự động cung cấp breaker per-instance. Đây là một thiết kế nâng cao, cần đánh giá số lượng instance, vòng đời breaker và cardinality metric trước khi triển khai.

## 9. Retry và CircuitBreaker có thể tác động lên số lần gọi

Spring Cloud LoadBalancer có thể được cấu hình retry cho một số loại lỗi hoặc request. Feign cũng có thể có cơ chế retry tùy client và cấu hình. Khi kết hợp retry với circuit breaker, cần xác định retry nằm bên trong hay bên ngoài ranh giới breaker.

Nếu LoadBalancer thực hiện nhiều lần thử bên trong một lần gọi Feign, circuit breaker có thể quan sát kết quả cuối cùng của lời gọi logic thay vì mỗi lần chọn instance như một sample độc lập. Chi tiết này phụ thuộc cách tích hợp và phiên bản đang dùng; hãy kiểm tra bằng log và thử nghiệm thay vì giả định số request HTTP bằng số lần breaker ghi nhận.

Một số nguyên tắc:

- Giới hạn tổng số lần retry và thời gian retry trong deadline của request.
- Không retry vô hạn khi registry không có instance.
- Chỉ retry lỗi có khả năng phục hồi và phù hợp với semantics của request.
- Cẩn trọng với thao tác ghi như reserve hoặc submit; timeout không chứng minh server chưa thực hiện lệnh.
- Dùng idempotency key hoặc mã thao tác để tránh tạo tác dụng phụ lặp lại.
- Tránh retry đồng thời ở nhiều tầng vì số request thực tế có thể tăng theo cấp số nhân.

Circuit breaker giúp ngừng các lời gọi mới khi phụ thuộc đang lỗi kéo dài. Retry xử lý một số lỗi thoáng qua. Hai cơ chế cần một ngân sách thời gian chung để không kéo dài request quá mức.

## 10. Kiểm tra metric và log theo từng tầng

Khi một lời gọi Feign thất bại, hãy xác định tầng gây lỗi trước khi điều chỉnh ngưỡng breaker:

- **Discovery:** service ID có được đăng ký không, instance có trạng thái nào, registry có dữ liệu mới không?
- **LoadBalancer:** instance nào được chọn, có retry không, có lỗi khi không tìm thấy instance không?
- **Feign/HTTP client:** request URL thực tế, connect timeout, read timeout, HTTP status và lỗi giải mã.
- **CircuitBreaker:** breaker name, trạng thái CLOSED/OPEN/HALF_OPEN, failure rate, slow call rate và số lần bị từ chối.
- **Fallback:** nguyên nhân truyền vào FallbackFactory và loại kết quả fallback được trả.

Spring Boot Actuator và Micrometer có thể xuất metric Resilience4j khi dependency và cấu hình metrics phù hợp. Tên metric và tag phụ thuộc phiên bản. Hãy kiểm tra endpoint metrics thực tế, xác nhận breaker name được dùng và bảo vệ endpoint quản trị.

Không gắn địa chỉ IP, request ID hoặc SKU làm tag metric nếu chúng tạo cardinality cao. Địa chỉ instance chi tiết phù hợp hơn với log có kiểm soát hoặc trace. Correlation ID có thể giúp nối log của order-service với inventory-service để xác định request đã đi qua instance nào.

## 11. Kiểm tra trạng thái phục hồi HALF_OPEN

Sau khi breaker chuyển OPEN và hết waitDurationInOpenState, breaker chuyển sang HALF_OPEN để cho phép số lời gọi thử giới hạn. Với Feign, các lời gọi thử vẫn đi qua đường LoadBalancer và có thể được phân phối đến các instance khác nhau.

Điều đó có nghĩa kết quả thử nghiệm có thể phụ thuộc instance được chọn:

- Nếu instance được chọn khỏe mạnh, breaker có thể nhận kết quả thành công.
- Nếu LoadBalancer chọn instance vẫn lỗi, breaker có thể quay lại OPEN.
- Nếu registry đã loại instance lỗi và chỉ còn instance khỏe, các lần thử có khả năng thành công hơn.

Không coi HALF_OPEN là health check trực tiếp cho từng instance. Breaker đang kiểm tra kết quả của lời gọi logic mà nó bảo vệ. Health check của registry/LoadBalancer và trạng thái breaker nên được quan sát riêng.

Khi thử phục hồi, ghi lại instanceId của từng request thử, kết quả HTTP, breaker state transition và thời điểm chuyển trạng thái. Điều này giúp phân biệt trường hợp dịch vụ đã phục hồi với trường hợp chỉ có một instance khỏe được chọn ngẫu nhiên.

## 12. Bài thực hành tổng hợp

Xây dựng order-service gọi inventory-service bằng OpenFeign, Service Discovery, LoadBalancer và Resilience4j:

1. Khai báo OpenFeign, LoadBalancer, discovery client và Resilience4j CircuitBreaker theo BOM tương thích.
2. Bật @EnableFeignClients và khai báo InventoryClient với name là inventory-service.
3. Không đặt URL cố định để Feign dùng service ID qua LoadBalancer.
4. Bật spring.cloud.openfeign.circuitbreaker.enabled.
5. Cấu hình FallbackFactory để phân biệt breaker OPEN, timeout và không tìm thấy instance.
6. Đăng ký hai instance inventory-service và xác nhận LoadBalancer phân phối lời gọi.
7. Làm một instance trả lỗi hoặc phản hồi chậm; quan sát lỗi và instance được chọn.
8. Tạo đủ số mẫu để breaker đạt ngưỡng mở; xác nhận lời gọi mới bị từ chối và fallback chạy.
9. Dừng toàn bộ instance để kiểm tra trường hợp discovery không tìm thấy đích.
10. Khởi động lại service và quan sát các lời gọi thử HALF_OPEN qua LoadBalancer.
11. Thử retry có giới hạn và xác định số HTTP attempt so với số lần gọi logic.
12. Đọc metric và log để phân biệt discovery, LoadBalancer, Feign, CircuitBreaker và fallback.

Kết quả cần đạt là bạn có thể mô tả chính xác một lời gọi Feign đi từ service ID đến instance được chọn, chỉ ra breaker đang bảo vệ ranh giới nào và giải thích vì sao trạng thái breaker không đại diện cho sức khỏe của từng instance riêng lẻ. Khi hiểu đúng các tầng, bạn có thể điều chỉnh health check, LoadBalancer, timeout, retry và circuit breaker mà không nhầm trách nhiệm giữa chúng.

## Tài liệu tham khảo

- Spring Cloud OpenFeign — CircuitBreaker Support: https://docs.spring.io/spring-cloud-openfeign/reference/spring-cloud-openfeign.html
- Spring Cloud LoadBalancer Reference: https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-loadbalancer.html
- Spring Cloud CircuitBreaker — Resilience4J: https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html

