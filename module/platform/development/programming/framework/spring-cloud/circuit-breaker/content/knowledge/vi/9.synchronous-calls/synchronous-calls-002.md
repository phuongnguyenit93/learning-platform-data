# Đặt ranh giới ngắt mạch quanh đúng thao tác từ xa

## Mục tiêu của bài học

Trong ứng dụng Spring Cloud, một phương thức nghiệp vụ thường thực hiện nhiều việc: kiểm tra đầu vào, đọc dữ liệu cục bộ, gọi một dịch vụ khác, chuyển đổi kết quả và lưu thay đổi. Circuit breaker cần theo dõi sức khỏe của một phụ thuộc từ xa cụ thể. Nếu đặt nó bao quanh toàn bộ phương thức nghiệp vụ, các lỗi cục bộ cũng có thể bị tính nhầm là lỗi của dịch vụ phụ thuộc.

Ranh giới phù hợp thường nằm tại nơi ứng dụng thực hiện một thao tác I/O từ xa. Ví dụ, lời gọi đọc tồn kho có breaker riêng, lời gọi định giá có breaker riêng. Mỗi breaker theo dõi đúng phụ thuộc mà nó bảo vệ và chỉ ghi nhận kết quả của thao tác đó.

Sau bài học, bạn có thể:

- Xác định đúng ranh giới của một lời gọi đồng bộ cần circuit breaker.
- Dùng CircuitBreakerFactory để bọc một thao tác từ xa bằng Supplier.
- Chọn id riêng cho từng phụ thuộc hoặc thao tác có đặc tính vận hành khác nhau.
- Tách lỗi của dịch vụ từ xa khỏi lỗi kiểm tra dữ liệu và xử lý nghiệp vụ cục bộ.
- Thiết kế fallback có ý nghĩa và không che giấu lỗi nghiệp vụ.
- Kiểm tra hành vi khi breaker ở CLOSED, OPEN và HALF_OPEN.

## 1. Ranh giới ngắt mạch là gì?

Giả sử order-service xử lý yêu cầu tạo đơn hàng. Một luồng đơn giản có thể gồm:

1. Kiểm tra mã sản phẩm và số lượng.
2. Đọc thông tin tồn kho từ inventory-service.
3. Lấy giá từ pricing-service.
4. Tính tổng tiền và áp dụng quy tắc giảm giá.
5. Lưu đơn hàng.

Trong luồng này, bước 2 và bước 3 là hai thao tác từ xa với hai phụ thuộc khác nhau. Circuit breaker nên được đặt tại từng ranh giới gọi đó:

    Client
      |
      v
    order-service
      |
      +-- validate request (local)
      |
      +-- [breaker: inventory-read] --> inventory-service
      |
      +-- [breaker: pricing-quote] --> pricing-service
      |
      +-- calculate total (local)
      |
      +-- save order (database)

Mỗi breaker theo dõi một thao tác gọi ra ngoài. Khi inventory-service lỗi, breaker inventory-read có thể mở. Lời gọi pricing-quote vẫn được đánh giá độc lập. Việc này ngăn lỗi của một phụ thuộc làm sai lệch thống kê hoặc chặn nhầm phụ thuộc khác.

Một ranh giới ngắt mạch phù hợp có ba đặc điểm:

- **Có một phụ thuộc rõ ràng:** thao tác được bảo vệ gọi đến một dịch vụ hoặc tài nguyên từ xa cụ thể.
- **Có kết quả có thể quan sát:** thành công, lỗi hoặc phản hồi chậm của thao tác có ý nghĩa với sức khỏe phụ thuộc.
- **Có chính sách phục hồi phù hợp:** khi breaker từ chối lời gọi, ứng dụng biết có thể dùng cache, trả trạng thái chưa xác định hay phải truyền lỗi lên tầng gọi.

Circuit breaker không phải lớp bao quanh mọi dòng code trong một phương thức. Nó là cơ chế bảo vệ lời gọi đến một phụ thuộc.

## 2. Vì sao không bọc toàn bộ phương thức nghiệp vụ?

Ví dụ sau đặt breaker quanh cả quy trình tạo đơn:

    public OrderResult createOrder(CreateOrderRequest request) {
        return circuitBreakerFactory.create("inventory").run(
            () -> {
                validate(request);
                Product product = productRepository.findById(request.productId())
                    .orElseThrow();
                InventoryResponse stock = inventoryClient.get()
                    .uri("/inventory/{sku}", request.sku())
                    .retrieve()
                    .body(InventoryResponse.class);
                BigDecimal total = calculateTotal(product, stock, request);
                orderRepository.save(Order.from(request, total));
                return OrderResult.created(total);
            },
            error -> OrderResult.unavailable()
        );
    }

Cách này có thể gây ra nhiều vấn đề:

- Nếu validate phát sinh lỗi do đầu vào không hợp lệ, breaker inventory vẫn có thể ghi nhận lỗi dù inventory-service chưa được gọi.
- Nếu cơ sở dữ liệu cục bộ lỗi, breaker inventory có thể mở sai lý do.
- Nếu phép tính nghiệp vụ phát sinh exception, fallback có thể che giấu lỗi logic.
- Nếu lưu đơn hàng đã thực hiện một phần rồi mới phát sinh lỗi, fallback có thể trả một kết quả chung chung trong khi trạng thái dữ liệu cần được xử lý rõ ràng.
- Khi pricing-service cũng nằm trong lambda, lỗi của pricing có thể bị ghi nhận vào breaker inventory.

Những lỗi đó không phản ánh sức khỏe của inventory-service. Chúng làm thống kê circuit breaker mất ý nghĩa và có thể khiến hệ thống từ chối các lời gọi đang khỏe mạnh.

Hãy giữ phần điều phối nghiệp vụ bên ngoài breaker. Chỉ bọc thao tác từ xa trong Supplier mà circuit breaker thực thi.

## 3. Dùng CircuitBreakerFactory để bọc một lời gọi đồng bộ

Spring Cloud CircuitBreaker cung cấp CircuitBreakerFactory để tạo breaker theo id. Phương thức run nhận một Supplier thực hiện lời gọi chính và một hàm fallback nhận Throwable:

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

        public InventoryResponse find(String sku) {
            CircuitBreaker breaker = circuitBreakerFactory.create("inventory-read");

            return breaker.run(
                () -> inventoryClient.get()
                    .uri("/inventory/{sku}", sku)
                    .retrieve()
                    .body(InventoryResponse.class),
                error -> InventoryResponse.unknown(sku)
            );
        }
    }

Supplier ở đây chỉ thực hiện một thao tác: gửi HTTP GET đến inventory-service và đọc phản hồi. Việc tạo breaker bằng id inventory-read giúp gắn trạng thái, cấu hình và metric với lời gọi đọc tồn kho.

InventoryResponse.unknown(sku) là phương thức minh họa do ứng dụng định nghĩa. Nó cần biểu diễn rõ rằng hệ thống chưa xác định được tồn kho. Không nên dùng giá trị mặc định như quantity = 0 nếu điều đó khiến tầng nghiệp vụ hiểu nhầm sản phẩm chắc chắn đã hết hàng.

Trong ứng dụng thực tế, RestClient cần được cấu hình base URL, timeout kết nối và timeout phản hồi phù hợp. Các cấu hình đó thuộc HTTP client. Circuit breaker đánh giá kết quả lời gọi và có thể từ chối các lần gọi tiếp theo khi phụ thuộc có dấu hiệu lỗi; nó không tự thay thế timeout mạng.

## 4. Giữ phần xử lý cục bộ bên ngoài Supplier

Một cách tổ chức rõ ràng là đặt lời gọi từ xa trong gateway hoặc adapter. Tầng nghiệp vụ gọi gateway như một phụ thuộc bình thường:

    @Service
    public class OrderService {

        private final InventoryGateway inventoryGateway;
        private final PricingGateway pricingGateway;
        private final OrderRepository orderRepository;

        public OrderService(
                InventoryGateway inventoryGateway,
                PricingGateway pricingGateway,
                OrderRepository orderRepository) {
            this.inventoryGateway = inventoryGateway;
            this.pricingGateway = pricingGateway;
            this.orderRepository = orderRepository;
        }

        public OrderResult createOrder(CreateOrderRequest request) {
            validate(request);

            InventoryResponse stock = inventoryGateway.find(request.sku());
            PricingResponse price = pricingGateway.quote(request.sku());

            Order order = calculateOrder(request, stock, price);
            orderRepository.save(order);

            return OrderResult.from(order);
        }
    }

Trong cấu trúc này:

- OrderService chịu trách nhiệm điều phối quy trình và quy tắc nghiệp vụ.
- InventoryGateway chịu trách nhiệm gọi inventory-service và bảo vệ đúng lời gọi đó.
- PricingGateway chịu trách nhiệm gọi pricing-service với breaker riêng.
- Repository chịu trách nhiệm thao tác cơ sở dữ liệu.

Nếu validate, calculateOrder hoặc orderRepository.save phát sinh lỗi, lỗi được xử lý theo chính sách của phần tương ứng. Breaker inventory chỉ nhận kết quả từ thao tác gọi inventory-service.

Không nhất thiết mọi dự án đều phải tạo một class gateway riêng cho từng endpoint. Có thể dùng một adapter có nhiều phương thức, miễn là mỗi Supplier được bọc chỉ chứa đúng thao tác từ xa cần bảo vệ và id breaker được chọn rõ ràng.

## 5. Chọn id theo phụ thuộc và thao tác

Id là tên định danh breaker được factory sử dụng. Tên này thường gắn với cấu hình và dữ liệu quan sát. Chọn id ổn định giúp theo dõi đúng thao tác qua các lần triển khai.

Ví dụ:

| Lời gọi | Id đề xuất | Lý do |
| --- | --- | --- |
| Đọc tồn kho | inventory-read | Theo dõi thao tác đọc inventory riêng. |
| Giữ hàng | inventory-reserve | Có thể có timeout, tải và chính sách lỗi khác thao tác đọc. |
| Lấy giá | pricing-quote | Phụ thuộc pricing-service độc lập. |
| Tra cứu hồ sơ khách hàng | customer-profile | Theo dõi phụ thuộc customer-service. |

Không nên dùng một id chung như remote-call cho mọi phụ thuộc. Khi đó, một dịch vụ lỗi có thể làm breaker mở và chặn cả những lời gọi đến dịch vụ khác.

Cũng không nên tạo id chứa dữ liệu biến đổi như SKU, orderId, userId hoặc requestId. Nếu mỗi yêu cầu tạo một breaker mới, số lượng instance tăng không giới hạn, mỗi breaker có quá ít mẫu và sliding window không còn đủ dữ liệu để đánh giá. Id nên phản ánh thao tác hoặc nhóm thao tác có đặc tính vận hành ổn định.

Nếu hai thao tác gọi cùng một dịch vụ nhưng có đặc tính rất khác nhau, chẳng hạn đọc nhanh và xuất báo cáo dài, có thể dùng hai id riêng. Nếu nhiều thao tác có cùng mục tiêu vận hành và cần dùng chung chính sách, cân nhắc groupName khi factory và cấu hình hỗ trợ. Dù dùng chung cấu hình nhóm, id vẫn giúp tách trạng thái breaker theo thao tác.

## 6. Bảo vệ từng phụ thuộc trong một quy trình có nhiều lời gọi

Giả sử order-service cần inventory và pricing. Hai lời gọi phải có breaker riêng:

    @Service
    public class OrderDependencies {

        private final RestClient inventoryClient;
        private final RestClient pricingClient;
        private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;

        public OrderDependencies(
                RestClient inventoryClient,
                RestClient pricingClient,
                CircuitBreakerFactory<?, ?> circuitBreakerFactory) {
            this.inventoryClient = inventoryClient;
            this.pricingClient = pricingClient;
            this.circuitBreakerFactory = circuitBreakerFactory;
        }

        public InventoryResponse inventory(String sku) {
            return circuitBreakerFactory.create("inventory-read").run(
                () -> inventoryClient.get()
                    .uri("/inventory/{sku}", sku)
                    .retrieve()
                    .body(InventoryResponse.class),
                error -> InventoryResponse.unknown(sku)
            );
        }

        public PricingResponse pricing(String sku) {
            return circuitBreakerFactory.create("pricing-quote").run(
                () -> pricingClient.get()
                    .uri("/prices/{sku}", sku)
                    .retrieve()
                    .body(PricingResponse.class),
                error -> PricingResponse.unavailable(sku)
            );
        }
    }

Khi inventory lỗi, breaker inventory-read có thể chuyển OPEN. Lời gọi pricing vẫn đi qua breaker pricing-quote và được đánh giá bằng số liệu riêng. Ngược lại, lỗi định giá không làm breaker tồn kho mở.

Nếu quy trình nghiệp vụ cần cả hai kết quả để tạo đơn hàng, tầng điều phối phải quyết định phải làm gì khi một gateway trả trạng thái suy giảm. Ví dụ, nếu không có giá đáng tin cậy, có thể dừng tạo đơn và yêu cầu thử lại. Nếu không có tồn kho, có thể lưu đơn ở trạng thái chờ xác minh. Những quyết định này thuộc nghiệp vụ, không nên ẩn bên trong fallback của breaker.

## 7. Phân loại lỗi trước khi cho breaker ghi nhận

Không phải mọi exception đều thể hiện phụ thuộc đang không khỏe. Ví dụ:

- Lỗi kết nối hoặc timeout có thể phản ánh dịch vụ từ xa không khả dụng.
- Lỗi HTTP 5xx thường cho thấy dịch vụ phụ thuộc gặp lỗi xử lý.
- Lỗi HTTP 4xx có thể là kết quả nghiệp vụ hoặc đầu vào không hợp lệ, không nhất thiết là lỗi sức khỏe dịch vụ.
- Lỗi kiểm tra dữ liệu ở order-service không nên được tính là lỗi inventory-service nếu xảy ra trước khi gọi mạng.

Resilience4j cho phép cấu hình exception được ghi nhận và exception được bỏ qua bằng recordExceptions và ignoreExceptions. Ví dụ minh họa:

    resilience4j:
      circuitbreaker:
        instances:
          inventory-read:
            recordExceptions:
              - org.springframework.web.client.ResourceAccessException
              - org.springframework.web.client.HttpServerErrorException
            ignoreExceptions:
              - org.springframework.web.client.HttpClientErrorException

Cấu hình này chỉ là ví dụ về cách phân loại. Hãy xác minh các lớp exception thực tế của HTTP client đang dùng và chính sách nghiệp vụ của API. Một số lỗi 4xx như 429 có thể biểu thị quá tải hoặc giới hạn tốc độ từ phía phụ thuộc và cần được xử lý riêng; không nên bỏ qua tất cả 4xx một cách máy móc.

Cấu hình recordExceptions cũng cần được xem xét cùng ignoreExceptions và mặc định của Resilience4j. Mục tiêu là breaker ghi nhận những lỗi cho biết phụ thuộc không thể phục vụ lời gọi, đồng thời không mở breaker vì lỗi nghiệp vụ hoặc lỗi lập trình cục bộ.

Fallback và việc ghi nhận lỗi là hai quyết định khác nhau. Hàm fallback của run có thể được gọi khi Supplier thất bại hoặc khi breaker từ chối lời gọi. Việc một exception có được tính vào failure rate hay không được quyết định bởi cấu hình của breaker. Không nên cho rằng một lỗi được fallback thì chắc chắn đã được ghi nhận là lỗi circuit breaker.

## 8. Thiết kế fallback theo ý nghĩa của dữ liệu

Fallback chạy khi thao tác chính không trả được kết quả theo cách bình thường. Một fallback tốt cần trả lời câu hỏi: tầng nghiệp vụ có thể tiếp tục với dữ liệu nào mà không đưa ra quyết định sai?

Một số lựa chọn:

| Loại phụ thuộc | Fallback có thể phù hợp | Điều cần kiểm soát |
| --- | --- | --- |
| Tra cứu tồn kho | Trả trạng thái UNKNOWN hoặc dữ liệu cache còn hạn. | Không khẳng định còn hàng hoặc hết hàng khi chưa có dữ liệu đáng tin cậy. |
| Lấy giá | Trả trạng thái không có giá hoặc yêu cầu thử lại. | Không dùng giá 0 hoặc giá cũ nếu nghiệp vụ không cho phép. |
| Hồ sơ tùy chọn | Dùng cache hoặc bỏ qua phần thông tin tùy chọn. | Chỉ áp dụng khi dữ liệu không bắt buộc cho quyết định chính. |
| Dịch vụ xác thực | Thường truyền lỗi để từ chối thao tác. | Không cấp quyền truy cập chỉ vì dịch vụ xác thực không khả dụng. |

Ví dụ fallback phân biệt breaker mở với lỗi hạ tầng:

    private InventoryResponse inventoryFallback(String sku, Throwable error) {
        if (error instanceof CallNotPermittedException) {
            return InventoryResponse.unavailable(sku);
        }

        if (error instanceof ResourceAccessException) {
            return InventoryResponse.unknown(sku);
        }

        throw new InventoryLookupException(
            "Cannot determine inventory for " + sku,
            error
        );
    }

CallNotPermittedException là dấu hiệu breaker đang OPEN hoặc không cho phép lời gọi thử tại thời điểm đó. ResourceAccessException thường xuất hiện khi có vấn đề truy cập tài nguyên mạng. InventoryLookupException là exception do ứng dụng định nghĩa. Các loại lỗi khác được truyền lên để tầng gọi quyết định xử lý.

Fallback cần nhanh, có giới hạn tài nguyên và không gọi ngược lại phụ thuộc đang lỗi. Nếu fallback dùng cache, phải kiểm tra tuổi dữ liệu và quy tắc nghiệp vụ. Nếu fallback cũng thất bại, lỗi cần được truyền lên một cách rõ ràng thay vì bị che giấu.

## 9. Trạng thái breaker và tác động lên đúng lời gọi

Với breaker inventory-read:

- **CLOSED:** Supplier gửi request đến inventory-service. Kết quả thành công, thất bại hoặc chậm được dùng để cập nhật thống kê theo cấu hình.
- **OPEN:** Supplier không được thực thi. Lời gọi bị từ chối nhanh và hàm fallback có thể trả trạng thái suy giảm.
- **HALF_OPEN:** Chỉ một số lời gọi thử được phép đi đến inventory-service. Kết quả thử giúp breaker quyết định đóng lại hay mở lại.

Nếu inventory-read chuyển OPEN, những thao tác được bảo vệ bằng id inventory-read sẽ bị ảnh hưởng. Breaker pricing-quote vẫn có trạng thái riêng. Đây là lý do quan trọng để đặt đúng ranh giới và chọn id đúng phụ thuộc.

Trạng thái breaker thường nằm trong bộ nhớ từng instance ứng dụng. Nếu order-service chạy nhiều pod, mỗi pod có thể có thống kê và trạng thái riêng. Không giả định một breaker mở trên một pod sẽ tự động làm breaker trên mọi pod mở cùng lúc.

## 10. Timeout và thời gian thực thi của Supplier

Circuit breaker có thể đánh dấu lời gọi chậm dựa trên slowCallDurationThreshold, nhưng việc đánh dấu chậm không tự động hủy thao tác mạng. Với lời gọi đồng bộ, cần cấu hình timeout ở HTTP client:

- Connect timeout giới hạn thời gian thiết lập kết nối.
- Response hoặc read timeout giới hạn thời gian chờ dữ liệu phản hồi theo khả năng của client.
- Circuit breaker dùng slowCallDurationThreshold và slowCallRateThreshold để đánh giá các lời gọi chậm trong cửa sổ thống kê.

Đặt timeout phù hợp với ngân sách thời gian của yêu cầu từ client đến order-service. Nếu timeout của HTTP client quá dài, luồng xử lý có thể bị giữ lâu trước khi Supplier kết thúc và breaker có cơ hội ghi nhận kết quả.

Không dùng circuit breaker như cơ chế thay thế timeout. Cũng không đặt timeout của phụ thuộc dài hơn nhiều so với thời gian tầng gọi phía trên có thể chờ. Với các tác vụ đồng bộ, khả năng hủy một lời gọi đang chạy phụ thuộc vào HTTP client và cách nó triển khai timeout.

## 11. Kiểm tra ranh giới bằng tình huống lỗi

Có thể xác minh thiết kế bằng các tình huống thử nghiệm có kiểm soát:

| Tình huống | Kết quả cần quan sát |
| --- | --- |
| Request thiếu SKU và validate thất bại | Breaker inventory-read không ghi nhận lời gọi vì Supplier chưa chạy. |
| inventory-service trả thành công | Breaker inventory-read ghi nhận thành công. |
| inventory-service mất kết nối | Lời gọi thất bại; fallback hoặc lỗi được xử lý theo chính sách. |
| inventory-service phản hồi chậm quá ngưỡng | Slow call được ghi nhận; breaker có thể mở khi tỷ lệ vượt ngưỡng. |
| pricing-service trả lỗi | Breaker pricing-quote ghi nhận kết quả của pricing; breaker inventory-read không bị ảnh hưởng. |
| Cơ sở dữ liệu order-service lỗi khi lưu | Lỗi lưu dữ liệu được xử lý ở tầng repository/nghiệp vụ, không tính nhầm cho inventory. |
| Breaker inventory-read đang OPEN | Supplier gọi inventory không được thực thi; fallback được gọi. |
| Phụ thuộc phục hồi ở HALF_OPEN | Chỉ số lời gọi thử được phép chạy; kết quả quyết định trạng thái tiếp theo. |

Khi kiểm tra, quan sát cả trạng thái breaker, số lời gọi được phép, số lời gọi bị từ chối, failure rate, slow call rate và thời gian phản hồi. Nếu breaker mở khi chỉ có lỗi validate hoặc lỗi database, hãy xem lại phạm vi Supplier và cách phân loại exception.

## 12. Bài thực hành: tách ranh giới inventory và pricing

Tạo một order-service có hai gateway đồng bộ:

1. InventoryGateway.find(sku) gọi inventory-service trong breaker inventory-read.
2. PricingGateway.quote(sku) gọi pricing-service trong breaker pricing-quote.
3. OrderService.validate(request) chạy trước hai gateway và nằm ngoài breaker.
4. OrderService.calculateOrder(...) xử lý kết quả ở ngoài breaker.
5. OrderRepository.save(...) lưu đơn hàng ở ngoài hai breaker.

Sau đó thử các tình huống:

- Làm inventory-service ngừng phản hồi và xác nhận breaker inventory-read mở sau khi đủ mẫu.
- Trong lúc inventory-read đang OPEN, gọi pricing-quote và xác nhận breaker pricing vẫn hoạt động độc lập.
- Gửi request không hợp lệ và xác nhận breaker inventory không ghi nhận lỗi nếu chưa thực hiện lời gọi.
- Làm database lỗi ở bước lưu đơn và xác nhận lỗi không làm breaker inventory hoặc pricing mở.
- Phục hồi inventory-service và quan sát các lời gọi thử ở HALF_OPEN.
- Kiểm tra fallback trả trạng thái UNKNOWN hoặc UNAVAILABLE đúng với hợp đồng của ứng dụng.

Khi hoàn thành, bạn cần chỉ ra được chính xác dòng code nào thực hiện I/O từ xa, Supplier nào được breaker bảo vệ, id nào gắn với phụ thuộc và những lỗi nào không nên ảnh hưởng đến failure rate. Một ranh giới rõ ràng giúp circuit breaker cung cấp số liệu đáng tin cậy và giới hạn sự cố ở đúng phụ thuộc đang gặp vấn đề.

