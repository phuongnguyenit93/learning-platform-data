# Kiến thức nền và trình tự học từ một lời gọi đến hệ thống nhiều dịch vụ

## Mục tiêu của bài học

Khi một ứng dụng chỉ gọi một dịch vụ khác, lỗi thường có vẻ cục bộ: yêu cầu thất bại hoặc phải chờ lâu. Trong hệ thống nhiều dịch vụ, cùng lỗi đó có thể giữ các luồng xử lý, chiếm kết nối, làm hàng đợi tăng lên và khiến những dịch vụ vốn khỏe mạnh cũng ngừng đáp ứng. Circuit breaker giúp giới hạn tác động này bằng cách theo dõi kết quả lời gọi và tạm ngừng gọi đến một phụ thuộc đang gặp sự cố.

Sau bài học, bạn có thể:

- Mô tả đường đi của một yêu cầu từ ứng dụng đơn giản đến chuỗi nhiều dịch vụ và giải thích cách lỗi lan truyền.
- Phân biệt ba trạng thái **CLOSED**, **OPEN**, **HALF_OPEN**, cùng vai trò của sliding window.
- Bọc một lời gọi đồng bộ hoặc reactive bằng Spring Cloud CircuitBreaker với Resilience4j.
- Kết hợp circuit breaker với timeout, fallback và bulkhead theo đúng trách nhiệm của từng cơ chế.
- Đọc các chỉ số cơ bản để biết circuit breaker đang bảo vệ dịch vụ như thế nào.

## 1. Bắt đầu từ một lời gọi đến dịch vụ phụ thuộc

Giả sử **order-service** cần gọi **inventory-service** để kiểm tra tồn kho trước khi xác nhận đơn hàng. Ở phiên bản đầu tiên, luồng xử lý rất đơn giản:

    Client -> order-service -> inventory-service

Nếu inventory-service phản hồi nhanh và ổn định, lời gọi diễn ra bình thường. Nhưng một phụ thuộc từ xa có thể gặp nhiều dạng lỗi:

- Không kết nối được vì tiến trình dừng, DNS lỗi hoặc mạng bị gián đoạn.
- Phản hồi lỗi HTTP do dịch vụ không xử lý được yêu cầu.
- Phản hồi quá chậm vì truy vấn cơ sở dữ liệu, khóa tranh chấp hoặc tải tăng cao.
- Chỉ một phần yêu cầu thất bại, trong khi những yêu cầu khác vẫn thành công.

Điểm khác biệt quan trọng giữa lời gọi trong cùng tiến trình và lời gọi qua mạng là ứng dụng gọi không kiểm soát được thời gian hoàn thành của ứng dụng nhận. Một lời gọi chậm có thể giữ luồng xử lý và kết nối trong suốt thời gian chờ. Khi nhiều yêu cầu cùng chờ, số luồng khả dụng giảm, hàng đợi tăng và chính order-service cũng bắt đầu phản hồi chậm.

Timeout giới hạn thời gian chờ của một lời gọi. Circuit breaker giải quyết một câu hỏi khác: khi các lần gọi gần đây cho thấy phụ thuộc đang lỗi hoặc quá chậm, có nên tiếp tục gửi thêm yêu cầu đến đó hay tạm thời từ chối ngay? Hai cơ chế thường cần đi cùng nhau.

## 2. Khi một lời gọi trở thành chuỗi nhiều dịch vụ

Một hệ thống thực tế có thể có thêm dịch vụ định giá và kho trung tâm:

    Client
      |
      v
    order-service
      |-- Circuit breaker: inventory --> inventory-service
      |                                   |
      |                                   +-- Circuit breaker: warehouse --> warehouse-service
      |
      +-- Circuit breaker: pricing -----> pricing-service

Một yêu cầu tạo đơn hàng có thể cần cả tồn kho lẫn giá. Bản thân inventory-service lại gọi warehouse-service. Nếu kho trung tâm bị chậm, các lời gọi từ inventory bị giữ lại. Inventory dần hết luồng xử lý, sau đó order phải chờ inventory và những yêu cầu tạo đơn mới cũng bị ảnh hưởng.

Circuit breaker được đặt tại ranh giới gọi đến phụ thuộc từ xa. Trong ví dụ trên, order có một breaker cho inventory và một breaker cho pricing; inventory có breaker riêng cho warehouse. Mỗi breaker theo dõi một phụ thuộc cụ thể, nhờ vậy sự cố ở warehouse không trực tiếp làm breaker của pricing mở.

Không nên gom mọi lời gọi ra ngoài vào một breaker dùng chung. Một dịch vụ có thể khỏe mạnh trong khi dịch vụ khác đang lỗi. Cũng không nên tạo breaker theo từng người dùng hoặc từng mã đơn hàng: số lượng instance khi đó tăng không kiểm soát và mỗi cửa sổ thống kê lại có quá ít dữ liệu. Hãy chọn tên theo phụ thuộc hoặc nhóm lời gọi có đặc tính vận hành tương đương, chẳng hạn inventory và pricing.

## 3. Ba trạng thái của circuit breaker

Circuit breaker thường được hiểu qua ba trạng thái:

| Trạng thái | Cách xử lý lời gọi | Điều kiện chuyển trạng thái |
| --- | --- | --- |
| **CLOSED** | Cho phép lời gọi đi đến dịch vụ phụ thuộc và ghi nhận kết quả. | Khi tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm vượt ngưỡng sau khi có đủ số mẫu, chuyển sang OPEN. |
| **OPEN** | Từ chối nhanh lời gọi mới, không gửi yêu cầu đến phụ thuộc. Ứng dụng có thể chạy fallback. | Sau thời gian chờ đã cấu hình, breaker chuyển sang HALF_OPEN. |
| **HALF_OPEN** | Chỉ cho phép một số lượng nhỏ lời gọi thử nghiệm để kiểm tra phụ thuộc đã phục hồi chưa. | Nếu các lời gọi thử đạt yêu cầu, trở về CLOSED; nếu vẫn lỗi hoặc quá chậm, quay lại OPEN. |

Luồng chuyển trạng thái:

    CLOSED -- lỗi hoặc chậm vượt ngưỡng --> OPEN
       ^                                    |
       |                                    | hết thời gian chờ
       |                                    v
       +---------- thử thành công ------- HALF_OPEN
                                            |
                                            +-- thử thất bại --> OPEN

Ở CLOSED, breaker không có nghĩa là mọi lời gọi đều thành công; nó chỉ cho phép lời gọi đi qua và tiếp tục thống kê. Ở OPEN, lời gọi bị chặn nhanh, thường phát sinh CallNotPermittedException từ Resilience4j. Ở HALF_OPEN, số lời gọi thử được giới hạn để tránh dồn tải lớn lên dịch vụ vừa phục hồi.

Trạng thái breaker thường được giữ trong bộ nhớ của từng tiến trình ứng dụng. Nếu order-service chạy nhiều instance, mỗi instance có thể có trạng thái và thống kê riêng; không mặc định rằng mọi instance sẽ mở breaker cùng một thời điểm.

## 4. Sliding window dùng để quyết định khi nào mở breaker

Breaker cần xem xét kết quả các lời gọi gần đây. Resilience4j cung cấp hai kiểu sliding window phổ biến:

- **COUNT_BASED**: cửa sổ chứa kết quả của một số lượng lời gọi gần nhất. Ví dụ slidingWindowSize bằng 20 nghĩa là thống kê trên tối đa 20 lời gọi gần nhất.
- **TIME_BASED**: cửa sổ chia theo các khoảng thời gian trong một khoảng quan sát. Kiểu này phù hợp khi muốn đánh giá lỗi theo nhịp thời gian thay vì theo số lượng yêu cầu.

Một số cấu hình liên quan:

- **slidingWindowSize**: kích thước cửa sổ theo số lời gọi hoặc số bucket thời gian, tùy kiểu cửa sổ.
- **minimumNumberOfCalls**: số lời gọi tối thiểu cần có trước khi tính tỷ lệ để ra quyết định. Khi chưa đủ mẫu, breaker chưa mở chỉ vì một vài lỗi đầu tiên.
- **failureRateThreshold**: ngưỡng phần trăm lời gọi thất bại.
- **slowCallDurationThreshold**: thời gian từ đó một lời gọi được xem là chậm.
- **slowCallRateThreshold**: ngưỡng phần trăm lời gọi chậm.

Ví dụ, với failureRateThreshold bằng 50, khi đã có đủ mẫu, tỷ lệ lỗi đạt hoặc vượt 50% có thể làm breaker mở. Breaker cũng có thể mở khi tỷ lệ lời gọi chậm vượt slowCallRateThreshold, ngay cả khi các lời gọi cuối cùng vẫn trả về thành công. Điều này hữu ích vì một dịch vụ phản hồi quá chậm cũng có thể làm cạn tài nguyên của bên gọi.

Sliding window không phải bộ giới hạn tốc độ yêu cầu. Nó dùng dữ liệu gần đây để đánh giá sức khỏe của lời gọi. Việc đặt kích thước cửa sổ, số mẫu tối thiểu và ngưỡng cần dựa trên lưu lượng bình thường, SLO và đặc điểm phụ thuộc; các con số trong ví dụ chỉ là điểm khởi đầu để thử nghiệm.

## 5. Tích hợp Spring Cloud CircuitBreaker với Resilience4j

Spring Cloud CircuitBreaker cung cấp một lớp trừu tượng để ứng dụng tạo và sử dụng circuit breaker. Resilience4j là một implementation phổ biến. Với ứng dụng Spring Boot dùng lời gọi đồng bộ, có thể thêm starter sau và quản lý phiên bản theo Spring Cloud release train tương thích với Spring Boot của dự án:

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
    </dependency>

Ví dụ sau dùng RestClient của Spring Framework 6.1 trở lên. Giả sử client đã được cấu hình base URL trỏ đến inventory-service:

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

        public InventoryResponse find(String sku) {
            return circuitBreakerFactory.create("inventory").run(
                () -> inventoryClient.get()
                    .uri("/inventory/{sku}", sku)
                    .retrieve()
                    .body(InventoryResponse.class),
                error -> InventoryResponse.unknown(sku)
            );
        }
    }

create("inventory") lấy breaker có tên inventory. Hàm thứ nhất thực hiện lời gọi thật. Hàm thứ hai là fallback được gọi khi lời gọi thất bại hoặc breaker đang OPEN. InventoryResponse.unknown(sku) là phương thức do ứng dụng định nghĩa để biểu diễn trạng thái chưa xác định; đây không phải API có sẵn của Spring.

Fallback cần phản ánh đúng mức độ chắc chắn của dữ liệu. Nếu không truy vấn được tồn kho, không nên trả về rằng sản phẩm chắc chắn còn hàng hoặc chắc chắn hết hàng. Có thể trả trạng thái UNKNOWN, dùng dữ liệu cache còn hạn nếu nghiệp vụ cho phép, hoặc yêu cầu người dùng thử lại. Fallback cũng cần nhanh và không gọi ngược lại đúng phụ thuộc đang lỗi. Nếu fallback phát sinh lỗi, lỗi đó vẫn có thể được truyền lên tầng gọi.

Cấu hình Resilience4j có thể đặt trong application.yml:

    resilience4j:
      circuitbreaker:
        instances:
          inventory:
            registerHealthIndicator: true
            slidingWindowType: COUNT_BASED
            slidingWindowSize: 20
            minimumNumberOfCalls: 10
            failureRateThreshold: 50
            slowCallDurationThreshold: 800ms
            slowCallRateThreshold: 60
            waitDurationInOpenState: 10s
            permittedNumberOfCallsInHalfOpenState: 3
            automaticTransitionFromOpenToHalfOpenEnabled: true

Đây là cấu hình minh họa cho breaker tên inventory. Khi có đủ ít nhất 10 mẫu trong cửa sổ, Resilience4j đánh giá tỷ lệ lỗi và lời gọi chậm. Nếu breaker mở, nó chờ 10 giây trước khi cho phép tối đa 3 lời gọi thử ở trạng thái HALF_OPEN. Sau khi chạy thử, breaker quyết định đóng lại hoặc mở lại dựa trên kết quả và các ngưỡng đã đặt.

Tên instance trong cấu hình phải khớp với tên truyền vào create("inventory"). Với phụ thuộc khác, tạo instance cấu hình riêng như pricing. Cần xác định rõ những exception nào được tính là lỗi và exception nào nên bỏ qua. Ví dụ, lỗi xác thực hoặc dữ liệu đầu vào không hợp lệ thường không nói lên sức khỏe của dịch vụ phụ thuộc; nếu tính chúng vào failure rate, breaker có thể mở sai lý do. Resilience4j hỗ trợ cấu hình recordExceptions và ignoreExceptions cho trường hợp này.

## 6. Phối hợp circuit breaker, timeout, fallback và bulkhead

Các cơ chế bảo vệ xử lý những rủi ro khác nhau:

| Cơ chế | Trách nhiệm | Điều cần nhớ |
| --- | --- | --- |
| Timeout | Giới hạn thời gian chờ của một lời gọi. | Đặt timeout ở HTTP client hoặc tầng giao tiếp thực tế; circuit breaker không tự dừng một lời gọi đang chạy. |
| Circuit breaker | Ngừng gửi lời gọi khi phụ thuộc có dấu hiệu lỗi hoặc chậm kéo dài. | Dùng thống kê và trạng thái để tránh tiếp tục dồn yêu cầu vào phụ thuộc đang gặp sự cố. |
| Fallback | Cung cấp cách phản hồi suy giảm khi lời gọi không thực hiện được. | Chỉ trả dữ liệu mặc định hoặc cache khi nghiệp vụ cho phép và phải biểu diễn rõ độ tin cậy. |
| Bulkhead | Giới hạn tài nguyên hoặc số lời gọi đồng thời dành cho một phụ thuộc. | Giúp một phụ thuộc chậm không chiếm hết luồng, kết nối hoặc năng lực xử lý của ứng dụng. |
| Retry | Thử lại một lời gọi có khả năng thành công ở lần tiếp theo. | Giới hạn số lần, có backoff và tránh khuếch đại tải khi dịch vụ đang quá tải. |

### Timeout

Circuit breaker có thể đánh dấu lời gọi là chậm dựa trên slowCallDurationThreshold, nhưng việc đo thời gian chậm không đồng nghĩa với hủy lời gọi. Với lời gọi HTTP đồng bộ, hãy cấu hình connect timeout và response/read timeout trên HTTP client. Timeout của client phải phù hợp với ngân sách thời gian mà tầng gọi phía trên có thể chờ.

Resilience4j TimeLimiter có thể giới hạn thời gian cho các tác vụ bất đồng bộ được hỗ trợ, chẳng hạn lời gọi dựa trên CompletableFuture. Có thể cấu hình instance như sau:

    resilience4j:
      timelimiter:
        instances:
          inventory:
            timeoutDuration: 900ms
            cancelRunningFuture: true

TimeLimiter không thay thế timeout của kết nối mạng. Việc hủy Future cũng không bảo đảm máy chủ từ xa đã dừng xử lý yêu cầu; hãy đặt timeout ở đúng HTTP client và kiểm tra hành vi hủy của thư viện đang dùng.

### Bulkhead

Bulkhead giới hạn số lời gọi đồng thời đến một phụ thuộc. Ví dụ, nếu inventory chỉ được phép nhận tối đa 24 lời gọi đồng thời từ một instance của order, các lời gọi vượt giới hạn có thể bị từ chối hoặc phải chờ theo cấu hình. Khi dùng Resilience4j Bulkhead kiểu semaphore, cấu hình có dạng:

    resilience4j:
      bulkhead:
        instances:
          inventory:
            maxConcurrentCalls: 24
            maxWaitDuration: 0ms

Giới hạn này áp dụng theo phạm vi instance của ứng dụng và cấu hình bulkhead đang dùng. Nếu hệ thống có nhiều pod, tổng số lời gọi đồng thời đến inventory có thể lớn hơn giới hạn của một pod. Hãy tính cả số instance khi chọn giới hạn. Thread-pool bulkhead là lựa chọn khác khi cần cô lập tác vụ bằng một pool luồng riêng; cần quản lý cả kích thước pool và hàng đợi để tránh chuyển điểm nghẽn sang nơi khác.

### Retry và thứ tự áp dụng

Retry hữu ích với lỗi thoáng qua, nhưng mỗi lần thử lại đều tạo thêm tải. Nếu nhiều tầng cùng retry, một yêu cầu ban đầu có thể tạo ra rất nhiều lời gọi thực tế. Chỉ retry những lỗi có khả năng phục hồi, giới hạn số lần thử, thêm backoff và jitter, đồng thời giữ tổng thời gian trong ngân sách của yêu cầu.

Không dùng retry để che một phụ thuộc đang lỗi kéo dài. Circuit breaker giúp dừng các lần gọi mới khi bằng chứng cho thấy tiếp tục thử sẽ gây hại. Khi kết hợp nhiều decorator, cần hiểu thứ tự thực thi để biết breaker ghi nhận một lần thử hay toàn bộ chuỗi retry; cấu hình thứ tự nhất quán và kiểm tra bằng tình huống lỗi có chủ đích.

## 7. Bảo vệ lời gọi reactive

Với ứng dụng dùng WebClient và Reactor, Spring Cloud CircuitBreaker có starter reactive riêng:

    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
    </dependency>

Có thể bọc một Mono bằng ReactiveCircuitBreakerFactory:

    import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
    import org.springframework.stereotype.Component;
    import org.springframework.web.reactive.function.client.WebClient;
    import reactor.core.publisher.Mono;

    @Component
    public class ReactiveInventoryGateway {

        private final WebClient inventoryClient;
        private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;

        public ReactiveInventoryGateway(
                WebClient inventoryClient,
                ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
            this.inventoryClient = inventoryClient;
            this.circuitBreakerFactory = circuitBreakerFactory;
        }

        public Mono<InventoryResponse> find(String sku) {
            return circuitBreakerFactory.create("inventory").run(
                inventoryClient.get()
                    .uri("/inventory/{sku}", sku)
                    .retrieve()
                    .bodyToMono(InventoryResponse.class),
                error -> Mono.just(InventoryResponse.unknown(sku))
            );
        }
    }

Trong luồng reactive, fallback trả về một publisher như Mono. Giữ chuỗi xử lý bất đồng bộ và tránh gọi block() trên luồng xử lý reactive, vì thao tác đó có thể làm mất lợi ích không chặn và gây nghẽn event loop. Cũng cần đặt timeout phù hợp cho WebClient; circuit breaker vẫn có vai trò thống kê lỗi và chặn lời gọi tiếp theo, còn timeout quyết định thời gian chờ của từng yêu cầu.

## 8. Theo dõi hiệu quả bảo vệ

Một circuit breaker chỉ hữu ích khi nhóm vận hành quan sát được lúc nào nó mở, vì sao nó mở và phụ thuộc có phục hồi hay chưa. Với Spring Boot Actuator và Micrometer, Resilience4j có thể xuất các metric về số lời gọi, kết quả thành công/thất bại, lời gọi chậm, tỷ lệ lỗi và trạng thái breaker. Có thể bắt đầu bằng các nhóm dữ liệu sau:

- Số lời gọi theo tên breaker và kết quả: thành công, thất bại hoặc bị từ chối khi breaker đang mở.
- Trạng thái hiện tại: CLOSED, OPEN hay HALF_OPEN.
- Failure rate và slow call rate so với ngưỡng cấu hình.
- Thời gian phản hồi của phụ thuộc và số lời gọi đang chạy.
- Số lần fallback được sử dụng và tỷ lệ phản hồi suy giảm.

Có thể dùng các endpoint Actuator như health và metrics; nếu xuất sang Prometheus, bổ sung registry Prometheus tương ứng và chỉ expose endpoint phù hợp với chính sách vận hành của ứng dụng. Tên metric cụ thể có thể khác theo phiên bản và cấu hình tích hợp, vì vậy hãy xem danh sách metric thực tế của ứng dụng thay vì giả định mọi tên đều có sẵn.

Khi đọc số liệu, hãy kết hợp trạng thái breaker với độ trễ và tỷ lệ lỗi của dịch vụ phụ thuộc. Breaker mở liên tục có thể chỉ ra phụ thuộc đang mất ổn định, timeout quá chặt, ngưỡng chưa phù hợp hoặc exception bị phân loại sai. Fallback tăng đột biến là dấu hiệu trải nghiệm người dùng đang ở chế độ suy giảm; nó không nên bị xem là hoạt động bình thường chỉ vì API vẫn trả HTTP thành công.

## 9. Trình tự học và thực hành

Đi theo từng bước sẽ giúp bạn nhận ra tác dụng của mỗi lớp bảo vệ trước khi kết hợp chúng:

| Bước | Nội dung thực hành | Kết quả cần quan sát |
| --- | --- | --- |
| 1. Một lời gọi | Tạo order-service gọi inventory-service và ghi nhận thời gian phản hồi. | Biết đường đi của yêu cầu và độ trễ bình thường. |
| 2. Lỗi và timeout | Làm inventory trả lỗi, ngắt kết nối hoặc phản hồi chậm; cấu hình timeout phía client. | Yêu cầu không chờ vô hạn và lỗi được xử lý rõ ràng. |
| 3. Circuit breaker | Tạo breaker inventory, cấu hình sliding window và các ngưỡng. | Quan sát chuyển trạng thái từ CLOSED sang OPEN, rồi HALF_OPEN. |
| 4. Fallback | Trả trạng thái chưa xác định hoặc dữ liệu cache hợp lệ khi breaker mở. | API có phản hồi suy giảm có chủ đích và không tạo dữ liệu sai. |
| 5. Nhiều phụ thuộc | Thêm pricing-service, sau đó cho inventory gọi warehouse; dùng breaker riêng cho từng phụ thuộc. | Một phụ thuộc lỗi không làm mọi lời gọi khác bị mở breaker theo. |
| 6. Bulkhead và retry | Giới hạn lời gọi đồng thời; thử retry có giới hạn với lỗi thoáng qua. | Tải được kiểm soát và không bị khuếch đại bởi nhiều lần thử. |
| 7. Reactive | Chuyển một lời gọi sang WebClient và bọc publisher bằng reactive circuit breaker. | Luồng xử lý vẫn không chặn và fallback trả về publisher. |
| 8. Quan sát | Bật Actuator/Micrometer, theo dõi trạng thái, độ trễ, lỗi và fallback. | Có dữ liệu để điều chỉnh ngưỡng dựa trên hành vi thực tế. |

Bài thực hành tổng hợp: xây dựng luồng tạo đơn hàng gồm order-service, inventory-service và pricing-service. Trước tiên đo độ trễ khi các dịch vụ khỏe mạnh. Sau đó chủ động làm inventory phản hồi chậm, trả lỗi và phục hồi. Quan sát lúc breaker mở, xác nhận các lời gọi mới bị từ chối nhanh, kiểm tra nội dung fallback, rồi theo dõi các lời gọi thử ở HALF_OPEN. Cuối cùng thêm warehouse phía sau inventory và tạo tải đồng thời để thấy bulkhead giới hạn ảnh hưởng như thế nào.

Khi hoàn thành, bạn nên giải thích được vì sao timeout, circuit breaker, fallback và bulkhead cần phối hợp; biết chọn ranh giới breaker theo phụ thuộc; và dùng metric để điều chỉnh cửa sổ cùng ngưỡng theo lưu lượng thật. Những lựa chọn này cần được kiểm chứng trong môi trường thử nghiệm có tải và lỗi mô phỏng trước khi áp dụng cho hệ thống đang phục vụ người dùng.

