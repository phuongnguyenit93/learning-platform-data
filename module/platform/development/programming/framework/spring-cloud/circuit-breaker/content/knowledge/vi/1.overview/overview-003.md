# Thất bại nhanh và duy trì khả năng phục vụ khi hệ thống phụ thuộc lỗi

Trong một hệ thống Spring Cloud gồm nhiều dịch vụ, một yêu cầu thường đi qua nhiều thành phần trước khi trả kết quả. Chẳng hạn, dịch vụ đặt hàng cần gọi dịch vụ tồn kho để xác nhận sản phẩm. Nếu dịch vụ tồn kho phản hồi chậm, các luồng xử lý của dịch vụ đặt hàng phải chờ lâu hơn. Khi số yêu cầu tăng, luồng và kết nối có thể bị chiếm hết; những yêu cầu vốn không cần tồn kho cũng bắt đầu chậm hoặc thất bại. Một sự cố cục bộ vì thế có thể lan thành lỗi dây chuyền.

Circuit breaker giúp giới hạn tác động đó. Khi số lần gọi lỗi hoặc chậm vượt ngưỡng, nó tạm ngừng gửi yêu cầu đến dịch vụ phụ thuộc và từ chối nhanh các lời gọi tiếp theo. Ứng dụng có thể trả dữ liệu dự phòng, kết quả suy giảm có kiểm soát hoặc thông báo phù hợp. Cơ chế này là một phần của chiến lược phục hồi trong Spring Cloud CircuitBreaker, thường được triển khai với Resilience4j.

## Vì sao cần thất bại nhanh?

Nếu mỗi lời gọi đến một dịch vụ đang gặp sự cố đều chờ hết thời gian chờ dài, hệ thống gọi có thể tích lũy nhiều yêu cầu đang xử lý. Các luồng, kết nối HTTP và bộ nhớ bị chiếm dụng, làm giảm khả năng phục vụ cả những chức năng vẫn khỏe mạnh.

Thất bại nhanh có ba mục tiêu:

- **Cô lập sự cố:** giới hạn số lời gọi tiếp tục đi đến một phụ thuộc đang lỗi.
- **Giải phóng tài nguyên:** tránh giữ luồng và kết nối trong thời gian chờ không cần thiết.
- **Duy trì chức năng cốt lõi:** cho phép ứng dụng trả kết quả dự phòng hoặc tiếp tục xử lý phần không phụ thuộc vào dịch vụ đang lỗi.

Circuit breaker không sửa chữa dịch vụ phụ thuộc, không đảm bảo mọi yêu cầu đều thành công và cũng không thay thế timeout. Nó quyết định khi nào nên cho phép lời gọi đi tiếp dựa trên kết quả quan sát được. Timeout giới hạn thời gian chờ của một lời gọi; bulkhead giới hạn tài nguyên dành cho một nhóm lời gọi; fallback xác định cách ứng dụng phản hồi khi lời gọi không thể hoàn thành bình thường.

Một luồng xử lý điển hình:

~~~mermaid
flowchart LR
    A[Yêu cầu đến dịch vụ] --> B[Circuit breaker]
    B -->|CLOSED hoặc HALF_OPEN| C[Dịch vụ phụ thuộc]
    C -->|Thành công| D[Kết quả bình thường]
    C -->|Lỗi hoặc quá chậm| E[Fallback]
    B -->|OPEN: từ chối nhanh| E
    E --> F[Kết quả suy giảm có kiểm soát]
~~~

## Ba trạng thái của circuit breaker

Circuit breaker có ba trạng thái chính. Trạng thái quyết định lời gọi được chuyển đến dịch vụ phụ thuộc hay bị từ chối nhanh.

| Trạng thái | Hành vi | Điều kiện chuyển trạng thái |
|---|---|---|
| **CLOSED** | Cho phép lời gọi đi đến dịch vụ phụ thuộc và ghi nhận kết quả. | Khi tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm vượt ngưỡng sau khi đã có đủ số mẫu, chuyển sang OPEN. |
| **OPEN** | Không gửi lời gọi mới đến dịch vụ phụ thuộc; từ chối nhanh để ứng dụng xử lý fallback. | Sau khoảng chờ được cấu hình, chuyển sang HALF_OPEN. Một số cấu hình có thể tự động chuyển trạng thái khi hết thời gian chờ. |
| **HALF_OPEN** | Chỉ cho phép một số lượng nhỏ lời gọi thăm dò để kiểm tra dịch vụ đã hồi phục chưa. | Nếu các lời gọi thăm dò đạt yêu cầu, chuyển về CLOSED. Nếu tiếp tục lỗi hoặc chậm vượt ngưỡng, quay lại OPEN. |

**CLOSED** là trạng thái hoạt động bình thường. Mỗi lời gọi được theo dõi để tính tỷ lệ lỗi và lời gọi chậm trong cửa sổ trượt. Không phải một lỗi đơn lẻ nào cũng làm circuit breaker mở; quyết định còn phụ thuộc vào số mẫu tối thiểu và các ngưỡng đã cấu hình.

**OPEN** là trạng thái ngắt mạch. Lời gọi mới bị từ chối ngay mà không phải chờ dịch vụ phụ thuộc. Với Resilience4j, trường hợp này thường được biểu diễn bằng ngoại lệ **CallNotPermittedException**. Lớp gọi có thể dùng fallback để trả dữ liệu cache hoặc trạng thái tạm thời.

**HALF_OPEN** giúp kiểm tra khả năng phục hồi mà không tạo ra một đợt tải lớn đột ngột. Ví dụ, chỉ cho phép ba lời gọi thăm dò. Nếu chúng thành công theo tiêu chí đã cấu hình, circuit breaker đóng lại. Nếu dịch vụ vẫn lỗi, mạch mở lại và tiếp tục chờ.

Không nên xem HALF_OPEN là bằng chứng dịch vụ đã khỏe hoàn toàn. Đây chỉ là một phép thử có giới hạn; cần tiếp tục theo dõi tỷ lệ lỗi, độ trễ và lưu lượng sau khi mạch đóng lại.

## Sliding window và cách xác định ngưỡng mở mạch

Resilience4j dùng **sliding window** để tính kết quả của các lời gọi gần đây. Có hai kiểu cửa sổ:

| Kiểu cửa sổ | Cách tính | Khi phù hợp |
|---|---|---|
| **COUNT_BASED** | Xét kết quả của N lời gọi gần nhất. | Lưu lượng tương đối ổn định hoặc muốn quyết định dựa trên số lần gọi. |
| **TIME_BASED** | Xét kết quả trong một khoảng thời gian gần nhất. | Lưu lượng biến động và muốn đánh giá sự cố theo thời gian. |

Ví dụ, cửa sổ COUNT_BASED có kích thước 20, số lời gọi tối thiểu là 10 và ngưỡng lỗi là 50%. Resilience4j chỉ bắt đầu đánh giá tỷ lệ khi đã có ít nhất 10 kết quả. Nếu trong tập mẫu được đánh giá có ít nhất một nửa lời gọi thất bại, circuit breaker có thể chuyển sang OPEN. Cửa sổ tiếp tục trượt khi có kết quả mới, nên các kết quả cũ dần rời khỏi phép tính.

Một số tham số quan trọng:

- **slidingWindowType:** chọn COUNT_BASED hoặc TIME_BASED.
- **slidingWindowSize:** số lời gọi hoặc độ dài cửa sổ, tùy kiểu đã chọn.
- **minimumNumberOfCalls:** số mẫu tối thiểu trước khi tính tỷ lệ.
- **failureRateThreshold:** tỷ lệ lỗi tối đa trước khi mở mạch.
- **slowCallDurationThreshold:** thời lượng từ đó một lời gọi được xem là chậm.
- **slowCallRateThreshold:** tỷ lệ lời gọi chậm có thể làm mở mạch.
- **waitDurationInOpenState:** thời gian giữ trạng thái OPEN trước khi thử phục hồi.
- **permittedNumberOfCallsInHalfOpenState:** số lời gọi thăm dò được phép ở HALF_OPEN.

Cần phân biệt tỷ lệ lỗi với tỷ lệ lời gọi chậm. Một dịch vụ có thể vẫn trả HTTP 200 nhưng mất quá nhiều thời gian; nếu chỉ theo dõi lỗi, hệ thống gọi vẫn có nguy cơ cạn tài nguyên. Ngược lại, nếu ngưỡng quá nhạy với một vài mẫu trong thời gian lưu lượng thấp, mạch có thể mở không cần thiết. Hãy chọn cửa sổ và ngưỡng theo lưu lượng thực tế, thời gian đáp ứng mục tiêu và mức độ quan trọng của chức năng.

## Tích hợp Spring Cloud CircuitBreaker với Resilience4j

Trong dự án Spring Boot, thêm starter Resilience4j của Spring Cloud CircuitBreaker và quản lý phiên bản bằng Spring Cloud BOM tương thích với phiên bản Spring Boot của dự án. Không nên tự chọn một phiên bản starter riêng lẻ khi dự án đã dùng BOM.

Ví dụ khai báo dependency Maven:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
</dependency>
~~~

Cấu hình dưới đây minh họa một circuit breaker có tên catalog. Tên instance phải khớp với tên truyền vào create("catalog") trong mã nguồn.

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      catalog:
        registerHealthIndicator: true
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
        automaticTransitionFromOpenToHalfOpenEnabled: true
  timelimiter:
    instances:
      catalog:
        timeoutDuration: 1s
        cancelRunningFuture: true
  bulkhead:
    instances:
      catalog:
        maxConcurrentCalls: 20
        maxWaitDuration: 0ms
~~~

Đây là cấu hình khởi đầu để minh họa các nhóm thiết lập. Cần kiểm tra cách tích hợp TimeLimiter và loại bulkhead mà phiên bản Spring Cloud CircuitBreaker/Resilience4j của dự án đang sử dụng hỗ trợ. Nếu ứng dụng dùng thread-pool bulkhead, hãy cấu hình nhóm thread-pool-bulkhead tương ứng và giới hạn cả kích thước hàng đợi. Một hàng đợi lớn có thể biến lỗi từ chối nhanh thành độ trễ kéo dài.

### Bọc lời gọi đồng bộ

Spring Cloud CircuitBreaker cung cấp CircuitBreakerFactory để tạo circuit breaker theo tên. Ví dụ sau dùng RestClient để gọi dịch vụ danh mục:

~~~java
@Service
public class CatalogClient {

    private final RestClient restClient;
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public CatalogClient(
            RestClient.Builder builder,
            CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.restClient = builder
                .baseUrl("http://catalog-service")
                .build();
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public ProductSummary findProduct(String sku) {
        return circuitBreakerFactory.create("catalog").run(
            () -> restClient.get()
                    .uri("/products/{sku}", sku)
                    .retrieve()
                    .body(ProductSummary.class),
            error -> ProductSummary.unavailable(sku)
        );
    }
}
~~~

Trong ví dụ, lời gọi HTTP chỉ được thực hiện khi circuit breaker cho phép. Nếu lời gọi thất bại hoặc mạch đang OPEN, hàm fallback trả về một kết quả suy giảm. ProductSummary.unavailable(sku) là phương thức minh họa của mô hình dữ liệu; trong ứng dụng thực tế, fallback có thể đọc dữ liệu gần nhất từ cache hoặc trả một trạng thái miền nghiệp vụ rõ ràng.

Fallback cần nhanh và có ý nghĩa. Không nên gọi lại chính dịch vụ đang lỗi bên trong fallback, vì điều đó tái tạo áp lực lên phụ thuộc. Cũng không nên biến mọi lỗi thành một kết quả có vẻ thành công, chẳng hạn trả danh sách rỗng khi danh sách rỗng có nghĩa là không có sản phẩm. Hãy phân biệt rõ dữ liệu dự phòng, dữ liệu không tồn tại và trạng thái chưa thể xác định.

### Bọc lời gọi reactive

Với WebClient và Reactor, dùng ReactiveCircuitBreakerFactory để giữ lời gọi trong chuỗi Mono:

~~~java
@Component
public class ReactiveCatalogClient {

    private final WebClient webClient;
    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;

    public ReactiveCatalogClient(
            WebClient.Builder builder,
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.webClient = builder
                .baseUrl("http://catalog-service")
                .build();
        this.circuitBreakerFactory = circuitBreakerFactory;
    }

    public Mono<ProductSummary> findProduct(String sku) {
        Mono<ProductSummary> request = webClient.get()
                .uri("/products/{sku}", sku)
                .retrieve()
                .bodyToMono(ProductSummary.class);

        return circuitBreakerFactory.create("catalog").run(
                request,
                error -> Mono.just(ProductSummary.unavailable(sku))
        );
    }
}
~~~

Trong luồng reactive, hãy giữ kiểu trả về Mono hoặc Flux xuyên suốt và tránh gọi block() để chờ kết quả. Việc chặn luồng có thể làm mất lợi ích của mô hình non-blocking và khiến tài nguyên bị chiếm dụng. Cũng cần cấu hình timeout kết nối và phản hồi cho HTTP client reactive để một yêu cầu mạng không treo quá lâu.

## Kết hợp circuit breaker, timeout và bulkhead

Ba cơ chế này giải quyết các khía cạnh khác nhau của cùng một vấn đề:

| Cơ chế | Giới hạn điều gì? | Vai trò |
|---|---|---|
| Circuit breaker | Số lời gọi tiếp tục đến phụ thuộc đang lỗi hoặc chậm. | Ngừng gọi khi tín hiệu lỗi vượt ngưỡng và thử lại có kiểm soát sau thời gian chờ. |
| Timeout / TimeLimiter | Thời gian một lời gọi được phép chờ. | Trả quyền điều khiển về ứng dụng khi phụ thuộc phản hồi quá chậm. |
| Bulkhead | Số lời gọi đồng thời hoặc tài nguyên xử lý dành cho một phụ thuộc. | Ngăn một phụ thuộc chiếm hết luồng, kết nối hoặc năng lực xử lý của dịch vụ gọi. |

**Timeout:** đặt thời gian chờ phù hợp với ngân sách đáp ứng của yêu cầu phía trên. Ví dụ, nếu API đặt hàng phải phản hồi trong hai giây, lời gọi tồn kho không thể tiêu thụ toàn bộ ngân sách đó. Cần cấu hình cả timeout của HTTP client như connect timeout và response/read timeout. TimeLimiter không đảm bảo máy chủ từ xa dừng xử lý ngay khi phía gọi hết thời gian; việc hủy tác vụ còn phụ thuộc vào HTTP client và cách tác vụ được thực thi.

**Bulkhead:** giới hạn số lời gọi đồng thời đến từng phụ thuộc. Semaphore bulkhead phù hợp khi muốn giới hạn đồng thời ngay trên luồng gọi. Thread-pool bulkhead tách lời gọi sang nhóm luồng riêng, giúp cô lập tài nguyên tốt hơn nhưng cần giới hạn số luồng và hàng đợi. Khi đạt giới hạn, lời gọi mới bị từ chối để ứng dụng xử lý fallback hoặc trả lỗi phù hợp.

**Thứ tự và phối hợp:** hãy đặt ngân sách timeout nhỏ hơn thời gian chờ tối đa của yêu cầu gọi ở tầng trên, đồng thời chọn giới hạn bulkhead theo năng lực thực tế của dịch vụ phụ thuộc. Retry chỉ nên dùng có giới hạn cho lỗi tạm thời có khả năng phục hồi. Retry quá nhiều lần hoặc retry khi circuit breaker đang OPEN có thể khuếch đại lưu lượng và làm sự cố nặng hơn.

## Theo dõi hiệu quả bảo vệ dịch vụ

Circuit breaker chỉ hữu ích khi nhóm vận hành biết nó đang ở trạng thái nào và vì sao trạng thái thay đổi. Có thể tích hợp Spring Boot Actuator và Micrometer với Resilience4j để quan sát các chỉ số như:

- Số lời gọi thành công, thất bại và bị từ chối do mạch OPEN.
- Tỷ lệ lỗi, tỷ lệ lời gọi chậm và độ trễ của phụ thuộc.
- Trạng thái CLOSED, OPEN hoặc HALF_OPEN.
- Số lần fallback được sử dụng và số lời gọi bị bulkhead từ chối.
- Số tác vụ đang chạy và độ dài hàng đợi nếu dùng thread-pool bulkhead.

Có thể bật health indicator cho instance bằng registerHealthIndicator. Chỉ công khai các endpoint Actuator cần thiết và bảo vệ chúng theo chính sách truy cập của môi trường triển khai.

Khi đọc số liệu, hãy xem xét cả tín hiệu kỹ thuật lẫn tác động nghiệp vụ. Mạch OPEN liên tục có thể cho thấy phụ thuộc chưa phục hồi hoặc timeout/ngưỡng chưa phù hợp. Fallback tăng đột biến có thể giữ API hoạt động nhưng cũng đồng nghĩa người dùng đang nhận dữ liệu suy giảm. Nếu mạch liên tục chuyển OPEN rồi CLOSED trong thời gian ngắn, cần đánh giá lại cửa sổ trượt, số mẫu tối thiểu, ngưỡng và thời gian chờ.

## Các bước thiết kế và kiểm thử

Khi bổ sung circuit breaker cho một lời gọi dịch vụ, có thể thực hiện theo trình tự sau:

1. Xác định phụ thuộc cần bảo vệ, chức năng nào có thể suy giảm và kết quả nào được phép trả về khi phụ thuộc không sẵn sàng.
2. Đo lưu lượng và độ trễ bình thường; xác định ngân sách thời gian của yêu cầu gọi để chọn timeout.
3. Chọn kiểu sliding window, kích thước cửa sổ, số mẫu tối thiểu và ngưỡng lỗi/lời gọi chậm.
4. Chọn thời gian OPEN và số lời gọi thăm dò HALF_OPEN phù hợp với khả năng phục hồi của phụ thuộc.
5. Giới hạn đồng thời bằng bulkhead và thiết kế fallback nhanh, rõ nghĩa, không gọi lại phụ thuộc đang lỗi.
6. Theo dõi trạng thái, tỷ lệ lỗi, độ trễ và tần suất fallback trong môi trường kiểm thử trước khi điều chỉnh ngưỡng cho môi trường thật.

Với một dịch vụ đặt hàng gọi dịch vụ tồn kho, hãy thử ít nhất các tình huống: dịch vụ tồn kho trả lỗi liên tục, phản hồi chậm hơn timeout, ngừng phản hồi hoàn toàn và phục hồi sau một khoảng thời gian. Quan sát circuit breaker chuyển từ CLOSED sang OPEN, từ OPEN sang HALF_OPEN rồi trở lại CLOSED khi các lời gọi thăm dò thành công. Đồng thời xác nhận yêu cầu bị từ chối nhanh vẫn nhận được phản hồi fallback có ý nghĩa, số lời gọi đồng thời không vượt giới hạn bulkhead và các chỉ số phản ánh đúng tình trạng.

Một cấu hình tốt không phải là cấu hình có nhiều ngưỡng nhất. Nó là cấu hình phù hợp với lưu lượng, ngân sách đáp ứng và mức độ suy giảm mà nghiệp vụ chấp nhận được. Hãy bắt đầu từ một phụ thuộc quan trọng, đo hành vi thực tế, rồi điều chỉnh từng tham số dựa trên số liệu.

