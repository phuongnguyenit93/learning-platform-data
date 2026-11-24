# Các khái niệm: lời gọi, lỗi, ngưỡng, trạng thái và phương án dự phòng

Trong module **SPRING_CLOUD_CIRCUIT_BREAKER**, ta học cách dùng Circuit Breaker trong Spring Cloud để bảo vệ một dịch vụ khi dịch vụ mà nó phụ thuộc phản hồi chậm hoặc không khả dụng. Mục tiêu của mẫu thiết kế này là ngăn một sự cố cục bộ lan thành lỗi dây chuyền: thay vì tiếp tục gửi yêu cầu đến một hệ thống đang quá tải, ứng dụng tạm ngừng lời gọi, trả kết quả dự phòng phù hợp và chỉ thử kết nối lại sau một khoảng thời gian.

Để hiểu cách tích hợp Resilience4j, cấu hình sliding window, fallback, timeout, bulkhead, lời gọi reactive và theo dõi hiệu quả bảo vệ, trước hết cần thống nhất năm khái niệm: lời gọi, lỗi, ngưỡng, trạng thái và phương án dự phòng.

## 1. Vì sao một lời gọi thất bại có thể gây lỗi dây chuyền?

Giả sử dịch vụ Đơn hàng gọi dịch vụ Kho để kiểm tra số lượng sản phẩm. Khi dịch vụ Kho hoạt động bình thường, lời gọi thường hoàn thành trong vài chục mili giây. Khi Kho gặp sự cố, mỗi lời gọi có thể mất vài giây mới timeout. Trong thời gian chờ, các luồng xử lý của dịch vụ Đơn hàng vẫn bị chiếm dụng. Số yêu cầu đồng thời tăng lên, hàng đợi dài hơn, bộ nhớ và kết nối bị sử dụng nhiều hơn. Cuối cùng, chính dịch vụ Đơn hàng cũng có thể chậm hoặc ngừng phục vụ dù bản thân nó không hỏng.

Nếu tiếp tục gọi Kho theo cùng một cách, hệ thống vừa tạo thêm tải cho dịch vụ đang gặp sự cố, vừa tiêu hao tài nguyên của dịch vụ gọi. Circuit Breaker tạo một cơ chế ngắt tạm thời:

1. Khi hệ thống khỏe, các lời gọi được chuyển đến dịch vụ phụ thuộc và kết quả được ghi nhận.
2. Khi tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm vượt ngưỡng đã cấu hình, Circuit Breaker mở mạch.
3. Trong lúc mạch mở, lời gọi mới bị từ chối nhanh. Ứng dụng có thể trả dữ liệu dự phòng hoặc thông báo dịch vụ tạm thời không sẵn sàng.
4. Sau thời gian chờ, Circuit Breaker cho phép một số lời gọi thử nghiệm để đánh giá khả năng phục hồi.

Circuit Breaker không sửa lỗi ở dịch vụ phụ thuộc. Nó kiểm soát cách dịch vụ gọi phản ứng trước sự cố, giúp giới hạn tác động và tạo thời gian để hệ thống phục hồi.

## 2. Lời gọi và kết quả được ghi nhận

**Lời gọi (call)** là một lần ứng dụng thực hiện thao tác đến hệ thống phụ thuộc, chẳng hạn gọi HTTP để lấy tồn kho, gọi RPC để tính phí hoặc truy vấn một dịch vụ bên ngoài. Circuit Breaker thường được đặt quanh thao tác có nguy cơ phụ thuộc vào tài nguyên hoặc hệ thống không nằm trong quyền kiểm soát trực tiếp của ứng dụng.

Một lời gọi có thể kết thúc theo các cách sau:

| Kết quả | Ý nghĩa | Cách Circuit Breaker xem xét |
| --- | --- | --- |
| Thành công | Nhận được kết quả hợp lệ trong thời gian chấp nhận được | Ghi nhận một lời gọi thành công |
| Thất bại | Gặp exception, lỗi kết nối hoặc lỗi được cấu hình là lỗi phụ thuộc | Ghi nhận một lời gọi thất bại |
| Chậm | Hoàn thành nhưng thời gian thực hiện vượt ngưỡng lời gọi chậm | Ghi nhận là lời gọi chậm; nó vẫn có thể là thành công |
| Bị từ chối | Mạch đang OPEN nên thao tác thực tế không được thực hiện | Trả lỗi từ chối nhanh, thường là CallNotPermittedException |

Phân biệt **thất bại** và **chậm** rất quan trọng. Một lời gọi có thể trả về HTTP 200 nhưng mất 8 giây; xét về giao thức, nó thành công, nhưng xét về trải nghiệm và năng lực phục vụ, nó có thể gây hại. Resilience4j cho phép theo dõi riêng tỷ lệ lỗi và tỷ lệ lời gọi chậm.

Không phải mọi exception đều nhất thiết thể hiện dịch vụ phụ thuộc đang hỏng. Ví dụ, một mã sản phẩm không tồn tại có thể là kết quả nghiệp vụ bình thường. Nếu coi mọi lỗi 404 là lỗi hạ tầng, Circuit Breaker có thể mở mạch dù dịch vụ Kho vẫn khỏe. Vì vậy, cần xác định loại exception nào được ghi nhận là lỗi và loại nào nên bỏ qua.

Một lời gọi bị từ chối khi mạch OPEN cũng khác với lời gọi đã được gửi đi nhưng thất bại. Ứng dụng nhận được phản hồi từ chính Circuit Breaker mà không tạo thêm tải lên dịch vụ phụ thuộc. Số liệu từ chối vẫn cần được theo dõi vì nó cho biết cơ chế bảo vệ đang can thiệp.

## 3. Ngưỡng và sliding window

Circuit Breaker không nên mở mạch chỉ vì một lời gọi đơn lẻ gặp lỗi. Nó cần quan sát một nhóm lời gọi gần đây, tính tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm, rồi so sánh với ngưỡng cấu hình.

**Sliding window (cửa sổ trượt)** là vùng dữ liệu mà Circuit Breaker dùng để tính các tỷ lệ này. Khi có kết quả lời gọi mới, dữ liệu cũ dần rời khỏi cửa sổ. Nhờ đó, quyết định phản ánh tình trạng gần đây của dịch vụ phụ thuộc thay vì giữ mãi lịch sử lỗi từ nhiều giờ trước.

Resilience4j hỗ trợ hai kiểu cửa sổ:

| Kiểu cửa sổ | Cách hoạt động | Khi phù hợp |
| --- | --- | --- |
| COUNT_BASED | Theo dõi một số lượng lời gọi gần nhất, ví dụ 20 lời gọi đã hoàn tất | Lưu lượng tương đối ổn định hoặc cần đánh giá theo số lần gọi |
| TIME_BASED | Theo dõi kết quả trong một khoảng thời gian, ví dụ 10 giây gần nhất | Lưu lượng biến động và cần đánh giá theo thời gian thực |

Một số tham số thường gặp:

- **slidingWindowType**: chọn COUNT_BASED hoặc TIME_BASED.
- **slidingWindowSize**: số lời gọi trong cửa sổ COUNT_BASED hoặc độ dài cửa sổ tính theo giây trong TIME_BASED.
- **minimumNumberOfCalls**: số lời gọi tối thiểu cần có trước khi tính tỷ lệ. Tham số này tránh quyết định từ một mẫu quá nhỏ.
- **failureRateThreshold**: ngưỡng tỷ lệ lỗi, tính theo phần trăm.
- **slowCallDurationThreshold**: thời lượng từ đó một lời gọi được xem là chậm.
- **slowCallRateThreshold**: ngưỡng tỷ lệ lời gọi chậm, tính theo phần trăm.

Ví dụ, cửa sổ COUNT_BASED có kích thước 20 và minimumNumberOfCalls bằng 10. Circuit Breaker cần ít nhất 10 kết quả lời gọi trước khi tính tỷ lệ. Khi đã đủ mẫu, nếu tỷ lệ lỗi đạt hoặc vượt 50%, mạch có thể chuyển sang OPEN. Nếu tỷ lệ lời gọi chậm đạt hoặc vượt ngưỡng slowCallRateThreshold, mạch cũng có thể mở dù nhiều lời gọi vẫn trả về kết quả thành công.

Hai tỷ lệ có ý nghĩa khác nhau:

$$
\text{Tỷ lệ lỗi} = \frac{\text{số lời gọi thất bại}}{\text{tổng lời gọi được ghi nhận}} \times 100\%
$$

$$
\text{Tỷ lệ lời gọi chậm} = \frac{\text{số lời gọi vượt ngưỡng thời gian}}{\text{tổng lời gọi được ghi nhận}} \times 100\%
$$

Ví dụ có 10 lời gọi được ghi nhận: 4 lời gọi thất bại, 3 lời gọi chậm nhưng thành công và 3 lời gọi thành công nhanh. Tỷ lệ lỗi là 40%; tỷ lệ lời gọi chậm là 30%. Nếu ngưỡng lỗi là 50% và ngưỡng chậm là 60%, riêng mẫu này chưa khiến mạch mở. Nếu 6 trong 10 lời gọi thất bại, tỷ lệ lỗi đạt 60% và vượt ngưỡng 50%.

Các kết quả chưa hoàn tất chưa thể đóng góp vào tỷ lệ của cửa sổ. Vì thế, cấu hình timeout của lời gọi cũng ảnh hưởng đến thời điểm Circuit Breaker nhận được kết quả để đánh giá.

### Ví dụ cấu hình Resilience4j

Với Spring Cloud CircuitBreaker dùng Resilience4j, có thể cấu hình một instance tên inventory trong application.yml:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 60
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 5
        automaticTransitionFromOpenToHalfOpenEnabled: true
~~~

Trong cấu hình này, một lời gọi kéo dài hơn 2 giây được xem là chậm. Khi đã có tối thiểu 10 kết quả trong cửa sổ, tỷ lệ lỗi từ 50% trở lên hoặc tỷ lệ lời gọi chậm từ 60% trở lên có thể làm mạch mở. Mạch giữ trạng thái OPEN trong 10 giây; sau đó chuyển sang HALF_OPEN và cho phép tối đa 5 lời gọi thử nghiệm theo cấu hình.

Các giá trị trên chỉ minh họa cách đọc cấu hình, không phải ngưỡng phù hợp cho mọi hệ thống. Cần chọn chúng dựa trên độ trễ bình thường, lưu lượng, thời gian timeout và mục tiêu phục vụ của từng dịch vụ.

## 4. Ba trạng thái CLOSED, OPEN và HALF_OPEN

Circuit Breaker vận hành chủ yếu qua ba trạng thái. Trạng thái quyết định lời gọi mới có được phép đi đến dịch vụ phụ thuộc hay không.

### CLOSED — mạch đóng

Đây là trạng thái hoạt động bình thường. Lời gọi được phép đi qua đến dịch vụ phụ thuộc. Circuit Breaker ghi nhận kết quả và thời gian thực hiện để cập nhật sliding window.

Khi số lượng mẫu đạt minimumNumberOfCalls, Circuit Breaker tính tỷ lệ lỗi và tỷ lệ lời gọi chậm. Nếu một trong các tỷ lệ đạt ngưỡng tương ứng, mạch chuyển sang OPEN. Nếu chưa đạt ngưỡng, mạch tiếp tục ở CLOSED.

### OPEN — mạch mở

Khi mạch OPEN, Circuit Breaker từ chối nhanh các lời gọi mới mà không gọi dịch vụ phụ thuộc. Điều này tránh việc tiếp tục gửi yêu cầu đến một hệ thống đang có dấu hiệu quá tải hoặc mất khả năng phục vụ.

Ứng dụng thường nhận được CallNotPermittedException khi lời gọi bị chặn. Nếu có fallback phù hợp, ứng dụng có thể trả kết quả dự phòng. Thời gian duy trì OPEN được điều khiển bởi waitDurationInOpenState.

Khi hết thời gian chờ, Circuit Breaker chuyển sang HALF_OPEN. Với Resilience4j, có thể bật automaticTransitionFromOpenToHalfOpenEnabled để việc chuyển trạng thái diễn ra tự động; nếu không, trạng thái có thể được chuyển khi có lời gọi tiếp theo sau thời gian chờ.

### HALF_OPEN — mạch nửa mở

HALF_OPEN là giai đoạn kiểm tra khả năng phục hồi. Circuit Breaker chỉ cho phép một số lượng lời gọi giới hạn đi đến dịch vụ phụ thuộc. Số lời gọi thử nghiệm được cấu hình bằng permittedNumberOfCallsInHalfOpenState.

- Nếu các kết quả thử nghiệm cho thấy dịch vụ đã phục hồi và các tỷ lệ nằm trong ngưỡng, Circuit Breaker chuyển về CLOSED.
- Nếu tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm tiếp tục vượt ngưỡng, Circuit Breaker chuyển lại OPEN và tiếp tục bảo vệ hệ thống.

Giới hạn số lời gọi thử nghiệm giúp tránh tạo ra một đợt tải lớn ngay khi dịch vụ vừa hoạt động trở lại. Các yêu cầu còn lại trong lúc HALF_OPEN có thể vẫn bị từ chối khi số lượt thử nghiệm được cấp đã hết.

Sơ đồ chuyển trạng thái:

~~~mermaid
stateDiagram-v2
    [*] --> CLOSED
    CLOSED --> OPEN: Tỷ lệ lỗi hoặc lời gọi chậm đạt ngưỡng
    OPEN --> HALF_OPEN: Hết waitDurationInOpenState
    HALF_OPEN --> CLOSED: Các lời gọi thử nghiệm đạt yêu cầu
    HALF_OPEN --> OPEN: Các lời gọi thử nghiệm tiếp tục vượt ngưỡng
~~~

Chu trình này giúp Circuit Breaker cân bằng hai mục tiêu: ngừng gọi khi dịch vụ có vấn đề và khôi phục lưu lượng có kiểm soát khi dịch vụ hoạt động trở lại.

## 5. Phương án dự phòng (fallback)

**Fallback** là cách ứng dụng phản hồi khi lời gọi chính không thể cung cấp kết quả. Trong Spring Cloud CircuitBreaker, fallback có thể được truyền cùng thao tác run. Khi thao tác chính ném exception hoặc Circuit Breaker từ chối lời gọi vì đang OPEN, hàm dự phòng có thể tạo ra kết quả thay thế.

Ví dụ, trang sản phẩm có thể hiển thị thông tin tồn kho gần nhất từ cache khi dịch vụ Kho tạm thời không phản hồi. Một API khác có thể trả trạng thái “chưa thể kiểm tra tồn kho” để giao diện thông báo cho người dùng. Kết quả dự phòng phải thể hiện đúng mức độ chắc chắn của dữ liệu.

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestTemplate;

@Service
public class InventoryClient {
    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final RestTemplate restTemplate;

    public InventoryClient(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            RestTemplate restTemplate) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.restTemplate = restTemplate;
    }

    public Inventory find(String sku) {
        CircuitBreaker circuitBreaker =
                circuitBreakerFactory.create("inventory");

        return circuitBreaker.run(
                () -> restTemplate.getForObject(
                        "http://inventory-service/items/{sku}",
                        Inventory.class,
                        sku),
                error -> Inventory.unavailable(sku)
        );
    }
}
~~~

Đoạn mã minh họa cách dùng Spring Cloud CircuitBreaker abstraction. CircuitBreakerFactory tạo circuit breaker có tên inventory; tên này cần khớp với instance được cấu hình trong application.yml. Hàm đầu tiên thực hiện lời gọi HTTP. Hàm thứ hai tạo kết quả dự phòng khi lời gọi chính không cung cấp được kết quả.

Trong ví dụ, Inventory.unavailable(sku) nên biểu diễn rõ trạng thái “không xác định được tồn kho”. Không nên tự động trả quantity bằng 0 nếu 0 có nghĩa là “đã xác nhận hết hàng”; hai trạng thái đó có ý nghĩa nghiệp vụ khác nhau. Nếu có cache hợp lệ, fallback có thể trả dữ liệu cache kèm thời điểm cập nhật để người dùng và hệ thống biết dữ liệu đã cũ.

Fallback cần tuân theo một số nguyên tắc:

- Không gọi lại chính dịch vụ đang gặp sự cố từ bên trong fallback, vì điều đó có thể tạo vòng lặp hoặc tiếp tục làm tăng tải.
- Không che giấu lỗi nghiệp vụ hoặc lỗi lập trình bằng một giá trị mặc định không đúng nghĩa.
- Ghi nhận số lần fallback được sử dụng để phát hiện khi hệ thống đang suy giảm dù API vẫn trả phản hồi.
- Giữ fallback đơn giản, nhanh và ít phụ thuộc. Nếu fallback cũng gọi một dịch vụ bên ngoài, nó có thể thất bại theo cùng cách.
- Xác định loại exception được ghi nhận. Lỗi đầu vào hoặc kết quả nghiệp vụ như “không tìm thấy sản phẩm” thường cần được xử lý riêng thay vì làm tăng tỷ lệ lỗi hạ tầng.

Fallback không đồng nghĩa với retry. Retry thực hiện lại lời gọi; fallback cung cấp phản hồi thay thế khi lời gọi chính thất bại hoặc bị từ chối. Retry không giới hạn có thể khuếch đại sự cố, nên nếu kết hợp retry với Circuit Breaker cần giới hạn số lần thử và chú ý thứ tự bọc các cơ chế.

## 6. Circuit Breaker phối hợp với timeout, bulkhead và reactive

Circuit Breaker, timeout và bulkhead giải quyết các phần khác nhau của cùng một vấn đề bảo vệ dịch vụ:

| Cơ chế | Câu hỏi mà cơ chế trả lời | Tác dụng |
| --- | --- | --- |
| Circuit Breaker | Có nên tiếp tục gọi dịch vụ đang có dấu hiệu lỗi không? | Tạm ngừng lời gọi khi tỷ lệ lỗi hoặc chậm vượt ngưỡng |
| Timeout / TimeLimiter | Một lời gọi được phép chờ tối đa bao lâu? | Giới hạn thời gian chờ và giúp giải phóng xử lý khi thao tác quá lâu |
| Bulkhead | Có bao nhiêu lời gọi được chạy đồng thời? | Giới hạn số tác vụ hoặc luồng đang dùng tài nguyên cho một phụ thuộc |

Ngưỡng slowCallDurationThreshold chỉ giúp Circuit Breaker nhận diện lời gọi chậm sau khi có kết quả đo được. Circuit Breaker tự nó không đảm bảo dừng một lời gọi đang treo. Cần đặt timeout ở HTTP client hoặc dùng TimeLimiter phù hợp để giới hạn thời gian chờ. Bulkhead tiếp tục giới hạn số lời gọi đồng thời, nhờ đó một dịch vụ chậm không chiếm hết tài nguyên của ứng dụng gọi.

Với ứng dụng reactive, Spring Cloud CircuitBreaker cung cấp ReactiveCircuitBreakerFactory. Có thể bọc một Mono hoặc Flux và cung cấp một publisher dự phòng:

~~~java
ReactiveCircuitBreaker circuitBreaker =
        reactiveCircuitBreakerFactory.create("inventory");

return circuitBreaker.run(
        webClient.get()
                .uri("/items/{sku}", sku)
                .retrieve()
                .bodyToMono(Inventory.class),
        error -> Mono.just(Inventory.unavailable(sku))
);
~~~

Đây là ví dụ khái quát cho một lời gọi trả về Mono. Trong luồng reactive, nên giữ thao tác trong chuỗi publisher và tránh gọi block() tùy tiện, vì block có thể làm mất lợi ích của mô hình không chặn. Cần cấu hình timeout và giới hạn tài nguyên phù hợp với client reactive đang sử dụng.

## 7. Theo dõi hiệu quả bảo vệ

Chỉ thấy API vẫn trả HTTP 200 chưa đủ để kết luận Circuit Breaker hoạt động tốt. Nếu nhiều phản hồi đến từ fallback, người dùng có thể vẫn nhận được câu trả lời trong khi dữ liệu từ dịch vụ phụ thuộc đã không còn sẵn sàng.

Nên quan sát các nhóm chỉ số sau:

- **Trạng thái mạch**: số instance đang CLOSED, OPEN hoặc HALF_OPEN; thời điểm và tần suất chuyển trạng thái.
- **Kết quả lời gọi**: số lời gọi thành công, thất bại, chậm và bị từ chối.
- **Tỷ lệ**: failure rate và slow call rate so với các ngưỡng đã đặt.
- **Fallback**: số lần fallback được gọi, tỷ lệ phản hồi dự phòng và tỷ lệ fallback thất bại.
- **Độ trễ**: thời gian phản hồi của lời gọi phụ thuộc và thời gian phản hồi cuối cùng của API.

Spring Cloud CircuitBreaker kết hợp Resilience4j có thể xuất số liệu qua Micrometer khi ứng dụng bật cấu hình metrics phù hợp. Với Spring Boot Actuator và hệ thống giám sát như Prometheus, nhóm vận hành có thể tạo dashboard và cảnh báo khi mạch OPEN quá lâu, liên tục dao động giữa OPEN và HALF_OPEN, hoặc tỷ lệ fallback tăng bất thường.

Khi đọc dashboard, cần phân biệt lỗi của dịch vụ phụ thuộc với lỗi do Circuit Breaker từ chối. Nếu số lời gọi bị từ chối tăng, điều đó cho thấy cơ chế đang chặn lưu lượng; cần xem đồng thời trạng thái mạch, tỷ lệ lỗi của lời gọi trước đó và sức khỏe của dịch vụ phụ thuộc để tìm nguyên nhân.

## 8. Cách chọn cấu hình và những lỗi thường gặp

Không có một bộ ngưỡng chung cho mọi dịch vụ. Một số điểm cần cân nhắc:

1. **Đo độ trễ bình thường trước khi đặt ngưỡng chậm.** Nếu dịch vụ thường phản hồi trong 300 ms, ngưỡng 2 giây có thể hợp lý để bắt sự suy giảm rõ rệt; nếu dịch vụ vốn cần vài giây, ngưỡng đó sẽ tạo cảnh báo sai.
2. **Chọn sliding window theo lưu lượng.** Cửa sổ quá nhỏ dễ phản ứng với biến động ngẫu nhiên; cửa sổ quá lớn có thể làm chậm việc phát hiện sự cố.
3. **Đặt minimumNumberOfCalls phù hợp.** Giá trị quá thấp khiến tỷ lệ được tính từ ít mẫu; giá trị quá cao khiến hệ thống phải chờ lâu mới có thể mở mạch.
4. **Phân loại exception theo ngữ nghĩa.** Lỗi nghiệp vụ, lỗi xác thực hoặc dữ liệu không tồn tại không nên mặc định bị xem như lỗi hạ tầng.
5. **Chọn thời gian OPEN và số lời gọi HALF_OPEN có kiểm soát.** Thời gian quá ngắn có thể khiến ứng dụng thử lại khi dịch vụ chưa hồi phục; số lời gọi thử quá lớn có thể tạo tải đột ngột.
6. **Thiết kế fallback có ý nghĩa rõ ràng.** Dữ liệu cũ, dữ liệu chưa xác định và dữ liệu xác nhận bằng 0 phải là các trạng thái khác nhau.
7. **Theo dõi cả kết quả dự phòng.** Một fallback luôn thành công có thể khiến tỷ lệ lỗi API nhìn bề ngoài rất thấp dù dịch vụ phụ thuộc đang hỏng.

Một Circuit Breaker thường được cấu hình theo từng phụ thuộc hoặc nhóm thao tác có đặc tính lỗi và mục tiêu độ trễ tương tự. Dùng chung một mạch cho nhiều dịch vụ không liên quan có thể khiến sự cố ở một dịch vụ chặn nhầm lời gọi đến dịch vụ khác.

## 9. Tình huống tổng hợp

Xét dịch vụ Đơn hàng gọi dịch vụ Kho với cấu hình inventory ở trên:

1. Ban đầu mạch CLOSED. Các lời gọi lấy tồn kho được thực hiện và kết quả được đưa vào cửa sổ trượt.
2. Dịch vụ Kho bắt đầu phản hồi chậm và phát sinh lỗi. Khi cửa sổ có đủ mẫu, tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm đạt ngưỡng, mạch chuyển sang OPEN.
3. Các yêu cầu kiểm tra tồn kho tiếp theo bị từ chối nhanh. Đơn hàng dùng dữ liệu cache nếu còn phù hợp, hoặc trả trạng thái chưa thể xác minh tồn kho.
4. Sau 10 giây, mạch chuyển sang HALF_OPEN và chỉ cho phép một số lời gọi thử nghiệm.
5. Nếu dịch vụ Kho phục hồi, các lời gọi thử nghiệm hoàn tất trong giới hạn và mạch trở lại CLOSED. Nếu lỗi vẫn tiếp diễn, mạch quay lại OPEN.

Khi phân tích tình huống này, hãy tự trả lời:

- Lời gọi nào được tính vào sliding window và vì sao một lời gọi bị từ chối khác một lời gọi thất bại?
- Điều gì khiến mạch chuyển từ CLOSED sang OPEN?
- minimumNumberOfCalls bảo vệ quyết định mở mạch như thế nào?
- Vì sao HALF_OPEN chỉ cho phép một số lời gọi thử nghiệm?
- Fallback nên trả dữ liệu gì để không nhầm “không xác định tồn kho” với “hết hàng”?
- Khi nào cần thêm timeout hoặc bulkhead bên cạnh Circuit Breaker?

Nắm chắc các khái niệm này giúp đọc được cấu hình Resilience4j, dự đoán hành vi của ứng dụng trong từng trạng thái và thiết kế phản hồi dự phòng có ý nghĩa. Đây là nền tảng để triển khai Circuit Breaker an toàn trong các lời gọi đồng bộ và reactive của hệ thống Spring Cloud.
