# Circuit Breaker là gì và ngăn lỗi lan truyền như thế nào

Trong hệ thống microservices, một yêu cầu của người dùng thường đi qua nhiều dịch vụ. Ví dụ, khi đặt hàng, dịch vụ Order có thể gọi Inventory để giữ hàng, Payment để thanh toán và Shipping để tính phí giao hàng. Nếu Inventory phản hồi chậm hoặc ngừng hoạt động, các yêu cầu Order phải chờ lâu hơn. Khi số yêu cầu chờ tăng lên, thread, connection và hàng đợi của Order có thể bị chiếm hết. Những dịch vụ khác gọi Order cũng bắt đầu chậm theo. Một lỗi ban đầu ở Inventory vì thế có thể lan thành sự cố trên toàn hệ thống.

Circuit Breaker (cầu dao ngắt mạch) là mẫu thiết kế giúp giới hạn tác động đó. Nó theo dõi kết quả và thời gian xử lý của các lời gọi đến một dịch vụ phụ thuộc. Khi nhận thấy dịch vụ phụ thuộc đang gặp vấn đề, Circuit Breaker tạm ngừng gửi lời gọi mới đến dịch vụ đó, trả lỗi hoặc chuyển sang phương án dự phòng trong thời gian ngắn. Sau một khoảng chờ, nó cho phép một số lời gọi thử để xác định dịch vụ đã phục hồi hay chưa.

Trong Spring Cloud, Spring Cloud CircuitBreaker cung cấp một lớp trừu tượng để ứng dụng sử dụng Circuit Breaker mà ít phụ thuộc vào thư viện triển khai cụ thể. Resilience4j là một lựa chọn phổ biến cho phần triển khai này. Bài học tập trung vào cách Circuit Breaker hoạt động, cách nó ngăn lỗi dây chuyền và những khái niệm cần biết trước khi cấu hình trong Spring Cloud.

## 1. Vì sao lỗi ở một dịch vụ có thể lan truyền?

Giả sử dịch vụ Order xử lý 100 yêu cầu mỗi giây và mỗi yêu cầu gọi Inventory. Bình thường Inventory phản hồi trong 50 ms. Khi Inventory gặp sự cố, thời gian phản hồi tăng lên 8 giây. Mỗi yêu cầu Order phải giữ tài nguyên trong suốt thời gian chờ. Nếu lưu lượng tiếp tục đến, số lời gọi đang chờ sẽ tăng nhanh.

Một số hệ quả thường gặp:

- **Cạn kiệt thread:** các thread xử lý yêu cầu bị giữ lại để chờ dịch vụ phụ thuộc, khiến yêu cầu mới không có thread để xử lý.
- **Cạn connection:** connection pool dành cho HTTP hoặc cơ sở dữ liệu bị chiếm bởi các lời gọi chưa hoàn tất.
- **Hàng đợi tăng:** yêu cầu tích tụ, làm độ trễ tăng ngay cả với những chức năng không cần dịch vụ đang lỗi.
- **Tải khuếch đại do retry:** nhiều tầng cùng thử lại một yêu cầu có thể tạo ra lượng lời gọi lớn hơn nhiều so với lưu lượng ban đầu.
- **Lỗi lan theo chuỗi:** các dịch vụ phụ thuộc lẫn nhau bắt đầu chậm hoặc từ chối yêu cầu, dù bản thân chúng vẫn hoạt động bình thường.

Timeout giúp giới hạn thời gian một lời gọi được phép chờ, nhưng nếu nhiều yêu cầu liên tục gọi vào dịch vụ đang lỗi, hệ thống vẫn có thể chịu tải lớn. Retry có thể hữu ích với lỗi thoáng qua, nhưng retry quá nhiều hoặc đồng loạt có thể làm dịch vụ đang phục hồi càng quá tải. Circuit Breaker bổ sung một cơ chế ngắt lời gọi trong một khoảng thời gian để dịch vụ gặp sự cố có cơ hội phục hồi và phần còn lại của hệ thống tiếp tục hoạt động.

## 2. Circuit Breaker hoạt động như thế nào?

Có thể hình dung Circuit Breaker giống cầu dao điện. Khi dòng điện vượt ngưỡng nguy hiểm, cầu dao ngắt mạch để bảo vệ phần còn lại của hệ thống. Trong phần mềm, “dòng điện” được thay bằng kết quả lời gọi và thời gian xử lý.

Circuit Breaker thường thực hiện các việc sau:

1. Cho phép lời gọi đi đến dịch vụ phụ thuộc khi trạng thái cho phép.
2. Ghi nhận lời gọi thành công, thất bại và lời gọi quá chậm.
3. Đánh giá các kết quả trong một cửa sổ trượt (sliding window).
4. Chuyển sang trạng thái OPEN khi tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm vượt ngưỡng cấu hình, sau khi đã có đủ số mẫu tối thiểu.
5. Từ chối nhanh các lời gọi mới trong thời gian OPEN. Ứng dụng có thể trả lỗi có kiểm soát hoặc dùng fallback.
6. Sau thời gian chờ, chuyển sang HALF_OPEN và chỉ cho phép một số lời gọi thăm dò.
7. Đóng mạch nếu các lời gọi thăm dò cho thấy dịch vụ đã phục hồi; mở lại nếu chúng tiếp tục thất bại.

Circuit Breaker không tự sửa dịch vụ phụ thuộc và cũng không bảo đảm mọi yêu cầu đều thành công. Mục tiêu của nó là giới hạn số lời gọi tiếp tục đi vào một dịch vụ đang có vấn đề, giảm thời gian chờ và bảo vệ tài nguyên của các dịch vụ gọi đến.

## 3. Ba trạng thái CLOSED, OPEN và HALF_OPEN

<figure>
<pre>
CLOSED
  |  Tỷ lệ lỗi hoặc lời gọi chậm vượt ngưỡng
  v
OPEN
  |  Hết thời gian chờ
  v
HALF_OPEN
  |  Thăm dò thành công        |  Thăm dò thất bại
  v                           v
CLOSED                      OPEN
</pre>
</figure>

### CLOSED — cho phép lời gọi

Đây là trạng thái hoạt động bình thường. Circuit Breaker cho phép lời gọi đi đến dịch vụ phụ thuộc và ghi nhận kết quả vào sliding window. Khi số lượng mẫu đạt mức tối thiểu, nó tính tỷ lệ lỗi và/hoặc tỷ lệ lời gọi chậm. Nếu các tỷ lệ này vượt ngưỡng, Circuit Breaker chuyển sang OPEN.

Ví dụ, cấu hình cửa sổ gồm 10 lời gọi, cần tối thiểu 5 lời gọi để đánh giá và ngưỡng lỗi là 50%. Khi có ít nhất 5 mẫu, nếu tỷ lệ lỗi đạt hoặc vượt 50%, Circuit Breaker có thể mở mạch. Với cửa sổ 10 lời gọi có 6 lời gọi thất bại, tỷ lệ lỗi là 60%.

### OPEN — ngắt lời gọi

Khi ở trạng thái OPEN, Circuit Breaker từ chối nhanh lời gọi mới mà không gọi đến dịch vụ phụ thuộc. Điều này tránh tiếp tục tiêu tốn thời gian chờ, thread và connection cho một dịch vụ đang được đánh giá là không khỏe.

Lời gọi bị từ chối có thể kích hoạt fallback nếu ứng dụng đã cung cấp fallback phù hợp. Nếu không có fallback, lỗi được chuyển lên tầng gọi để xử lý. Circuit Breaker giữ trạng thái OPEN trong khoảng thời gian được cấu hình, thường gọi là thời gian chờ ở trạng thái mở.

### HALF_OPEN — thăm dò khả năng phục hồi

Khi thời gian chờ OPEN kết thúc, Circuit Breaker chuyển sang HALF_OPEN. Nó cho phép một số lượng giới hạn lời gọi đi qua để kiểm tra dịch vụ phụ thuộc. Số lời gọi thăm dò được điều khiển bởi cấu hình như permittedNumberOfCallsInHalfOpenState trong Resilience4j.

Nếu các lời gọi thăm dò cho thấy dịch vụ hoạt động ổn định, Circuit Breaker chuyển về CLOSED và tiếp tục ghi nhận kết quả bình thường. Nếu chúng tiếp tục thất bại hoặc quá chậm theo điều kiện cấu hình, Circuit Breaker quay lại OPEN. Giới hạn số lời gọi thăm dò giúp tránh dồn một lượng lớn lưu lượng vào dịch vụ ngay khi nó vừa bắt đầu phục hồi.

## 4. Sliding window và cách đánh giá lỗi

Circuit Breaker không nên mở mạch chỉ vì một lời gọi đơn lẻ thất bại. Một lỗi có thể xuất hiện do mạng chập chờn, dữ liệu đầu vào hoặc một tình huống nhất thời. Sliding window giúp đánh giá một nhóm kết quả gần đây thay vì chỉ nhìn vào kết quả cuối cùng.

Resilience4j hỗ trợ hai kiểu cửa sổ phổ biến:

| Kiểu cửa sổ | Cách hoạt động | Khi phù hợp |
| --- | --- | --- |
| COUNT_BASED | Giữ kết quả của một số lượng lời gọi gần nhất, chẳng hạn 20 lời gọi. | Lưu lượng tương đối ổn định hoặc muốn đánh giá theo số mẫu. |
| TIME_BASED | Tổng hợp kết quả trong một khoảng thời gian, chẳng hạn 30 giây gần nhất. | Lưu lượng thay đổi và muốn đánh giá theo thời gian thực. |

Một số tham số quan trọng:

- **slidingWindowType:** chọn COUNT_BASED hoặc TIME_BASED.
- **slidingWindowSize:** số lời gọi trong cửa sổ hoặc số giây của cửa sổ, tùy kiểu đã chọn.
- **minimumNumberOfCalls:** số lời gọi tối thiểu cần có trước khi tính tỷ lệ. Tham số này tránh kết luận từ một mẫu quá nhỏ.
- **failureRateThreshold:** tỷ lệ phần trăm lời gọi thất bại khiến Circuit Breaker mở mạch.
- **slowCallDurationThreshold:** thời lượng từ đó một lời gọi được xem là chậm.
- **slowCallRateThreshold:** tỷ lệ phần trăm lời gọi chậm khiến Circuit Breaker mở mạch.

Lời gọi chậm cũng có thể gây cạn tài nguyên dù cuối cùng nó trả về thành công. Vì vậy, theo dõi cả lỗi và độ trễ giúp Circuit Breaker phản ứng trước khi dịch vụ phụ thuộc hoàn toàn ngừng hoạt động.

Cần chọn cửa sổ và ngưỡng theo đặc tính của từng dịch vụ. Một dịch vụ có lưu lượng thấp có thể cần cửa sổ thời gian dài hơn hoặc số mẫu tối thiểu phù hợp. Một dịch vụ có độ trễ bình thường vốn cao cũng cần ngưỡng slow call riêng. Không nên sao chép một bộ ngưỡng cho mọi dependency mà không dựa trên dữ liệu vận hành.

## 5. Spring Cloud CircuitBreaker và Resilience4j

Spring Cloud CircuitBreaker cung cấp API thống nhất để ứng dụng gọi một Circuit Breaker. Phần triển khai phía dưới có thể là Resilience4j hoặc một provider được Spring Cloud hỗ trợ. Nhờ lớp trừu tượng này, mã nghiệp vụ có thể tập trung vào lời gọi và cách xử lý kết quả, còn cấu hình provider quyết định các ngưỡng và hành vi bảo vệ.

Với ứng dụng Spring Boot dùng Resilience4j, dependency thường dùng là starter sau (phiên bản cần tương thích với Spring Boot và Spring Cloud release train của dự án):

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-resilience4j</artifactId>
</dependency>
~~~

Ví dụ dưới đây minh họa một lời gọi đồng bộ từ Order đến Inventory. Ứng dụng lấy Circuit Breaker theo tên inventory, gọi client khi mạch cho phép và cung cấp fallback để trả về trạng thái tồn kho tạm thời không khả dụng.

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    public CatalogService(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public Inventory getInventory(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.getInventory(sku),
            error -> Inventory.unavailable(sku)
        );
    }
}
~~~

InventoryClient và Inventory là các kiểu thuộc ứng dụng minh họa. Phương thức unavailable cần tạo ra một kết quả miền nghiệp vụ biểu thị rõ rằng dữ liệu tồn kho hiện không khả dụng. Tên inventory là định danh cấu hình của Circuit Breaker; nên dùng tên ổn định theo dependency hoặc thao tác được bảo vệ.

Fallback cần được thiết kế cẩn thận. Ví dụ, với trang sản phẩm, ứng dụng có thể trả về dữ liệu tồn kho gần nhất từ cache kèm thông tin dữ liệu đã cũ. Với chức năng bắt buộc phải biết tồn kho chính xác trước khi xác nhận đơn hàng, ứng dụng có thể trả lỗi có kiểm soát và yêu cầu người dùng thử lại. Không nên biến lỗi thành một kết quả “thành công” giả, vì điều đó khiến tầng gọi hiểu sai trạng thái nghiệp vụ.

## 6. Cấu hình Resilience4j cơ bản

Có thể cấu hình từng Circuit Breaker trong application.yml. Ví dụ sau tạo cấu hình riêng cho dependency inventory:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 5
        failureRateThreshold: 50
        slowCallDurationThreshold: 2s
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
        automaticTransitionFromOpenToHalfOpenEnabled: true
~~~

Với cấu hình minh họa này, Circuit Breaker đánh giá tối đa 10 lời gọi gần nhất và chỉ bắt đầu tính tỷ lệ sau ít nhất 5 lời gọi. Nếu tỷ lệ lỗi đạt ngưỡng 50% hoặc tỷ lệ lời gọi chậm đạt ngưỡng 50%, mạch có thể chuyển sang OPEN. Một lời gọi kéo dài từ 2 giây được tính là chậm. Sau 10 giây ở OPEN, Circuit Breaker chuyển sang HALF_OPEN để cho phép tối đa 3 lời gọi thăm dò.

Đây chỉ là điểm bắt đầu để minh họa cách các tham số liên kết với nhau. Trong môi trường thật, cần chọn ngưỡng dựa trên lưu lượng, độ trễ bình thường, mục tiêu thời gian phản hồi và mức độ quan trọng của dependency. Nếu hệ thống có lưu lượng thấp, cấu hình minimumNumberOfCalls quá cao có thể khiến Circuit Breaker mất nhiều thời gian mới đánh giá được tình trạng dịch vụ.

Có thể tinh chỉnh loại exception được tính là lỗi. Chẳng hạn, lỗi kết nối và timeout thường cần được tính vào failure rate; một lỗi nghiệp vụ như sản phẩm không tồn tại có thể không nên làm Circuit Breaker mở mạch. Resilience4j hỗ trợ các thuộc tính recordExceptions và ignoreExceptions để kiểm soát việc ghi nhận exception. Hãy phân loại theo ý nghĩa nghiệp vụ và cách client biểu diễn lỗi, thay vì mặc định coi mọi exception đều giống nhau.

## 7. Kết hợp Circuit Breaker với timeout, retry và bulkhead

Circuit Breaker là một phần của khả năng phục hồi, không thay thế các cơ chế bảo vệ khác.

| Cơ chế | Vấn đề giải quyết | Cách phối hợp |
| --- | --- | --- |
| Timeout | Một lời gọi chờ quá lâu. | Đặt giới hạn thời gian cho lời gọi để giải phóng tài nguyên; timeout cần được nhận diện như một kết quả lỗi phù hợp. |
| Retry | Lỗi tạm thời có thể thành công khi thử lại. | Chỉ retry có giới hạn, có backoff và jitter khi thao tác an toàn để thử lại. Tránh retry liên tục khi Circuit Breaker đã mở. |
| Bulkhead | Một dependency chiếm hết tài nguyên dùng chung. | Giới hạn số lời gọi đồng thời hoặc cô lập thread pool để sự cố ở một dependency không chiếm toàn bộ năng lực xử lý. |
| Fallback | Tầng gọi cần hành vi có kiểm soát khi dependency không dùng được. | Trả dữ liệu cache, kết quả suy giảm hoặc lỗi nghiệp vụ rõ ràng tùy yêu cầu. |

Timeout đặc biệt quan trọng vì Circuit Breaker chỉ có thể đánh giá một lời gọi sau khi nhận được kết quả hoặc lỗi. Nếu lời gọi không có giới hạn thời gian và cứ treo, tài nguyên vẫn bị giữ lại trong thời gian dài. Với lời gọi bất đồng bộ, có thể kết hợp TimeLimiter của Resilience4j và kiểm tra khả năng hủy tác vụ khi hết thời gian.

Bulkhead giới hạn mức độ đồng thời của các lời gọi. Ví dụ, nếu Inventory chậm, một bulkhead có thể giới hạn số yêu cầu đang gọi Inventory, để các luồng xử lý khác vẫn còn tài nguyên. Resilience4j có các triển khai bulkhead dựa trên semaphore hoặc thread pool; lựa chọn phụ thuộc vào mô hình thực thi của ứng dụng.

Retry cần có ngân sách rõ ràng. Nếu mỗi tầng trong một chuỗi gồm ba dịch vụ đều thử lại ba lần, số lời gọi đến tầng cuối có thể tăng mạnh. Hãy giới hạn số lần thử, đặt backoff, thêm jitter và tránh retry các lỗi không thể phục hồi bằng cách gọi lại. Circuit Breaker và Retry cần được cấu hình cùng nhau để khi dependency đang lỗi, hệ thống không tiếp tục tạo thêm tải.

## 8. Lời gọi reactive

Với ứng dụng dùng Spring WebFlux và Reactor, Spring Cloud CircuitBreaker cung cấp ReactiveCircuitBreakerFactory. Circuit Breaker bọc một Publisher như Mono, để lời gọi và fallback vẫn nằm trong luồng reactive.

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ReactiveCatalogService {

    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final ReactiveInventoryClient inventoryClient;

    public ReactiveCatalogService(
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory,
            ReactiveInventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public Mono<Inventory> getInventory(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            inventoryClient.getInventory(sku),
            error -> Mono.just(Inventory.unavailable(sku))
        );
    }
}
~~~

Trong ví dụ, getInventory của ReactiveInventoryClient trả về Mono<Inventory>. Fallback cũng trả về Mono để giữ kiểu dữ liệu reactive. Cần tránh gọi block() trong luồng WebFlux vì thao tác chặn có thể chiếm event loop và làm mất lợi ích của mô hình non-blocking. Với reactive flow, cũng cần kiểm tra timeout, hủy subscription và bulkhead có tương thích với cách thực thi của ứng dụng hay không.

## 9. Theo dõi hoạt động của Circuit Breaker

Một Circuit Breaker được cấu hình đúng vẫn cần được quan sát trong môi trường chạy thật. Các chỉ số hữu ích gồm:

- Số lời gọi thành công, thất bại và bị Circuit Breaker từ chối.
- Tỷ lệ lỗi và tỷ lệ lời gọi chậm theo từng dependency.
- Số lần chuyển trạng thái CLOSED, OPEN và HALF_OPEN.
- Thời gian Circuit Breaker ở trạng thái OPEN.
- Số lần fallback được sử dụng và tỷ lệ fallback thành công.
- Độ trễ của lời gọi đến dependency và độ trễ mà người dùng thực sự nhận được.

Resilience4j có tích hợp Micrometer để xuất metrics; Spring Boot Actuator có thể được dùng để công bố endpoint metrics và health theo cấu hình của ứng dụng. Khi bật health indicator, cần hiểu cách trạng thái Circuit Breaker ảnh hưởng đến trạng thái health tổng thể. Một dependency đang OPEN không nhất thiết có nghĩa toàn bộ ứng dụng phải bị đánh dấu DOWN, đặc biệt khi ứng dụng vẫn có thể phục vụ chức năng suy giảm bằng cache hoặc fallback.

Nên gắn tên Circuit Breaker với dependency hoặc thao tác rõ ràng, đồng thời đưa các chỉ số vào dashboard và cảnh báo. Nếu một Circuit Breaker thường xuyên OPEN, hãy kiểm tra log, trace, tỷ lệ lỗi của dependency, thời gian phản hồi và cấu hình timeout. Nếu fallback tăng đột biến, người vận hành cần biết người dùng đang nhận dữ liệu cũ, kết quả suy giảm hay lỗi từ chối.

## 10. Những nguyên tắc khi thiết kế

- **Đặt Circuit Breaker quanh lời gọi từ xa:** áp dụng cho dependency có thể chậm hoặc không khả dụng như HTTP service, RPC hoặc một hệ thống bên ngoài.
- **Tách cấu hình theo dependency:** mỗi dịch vụ có lưu lượng, độ trễ và mức độ quan trọng khác nhau.
- **Chọn exception có ý nghĩa:** lỗi nghiệp vụ thông thường không nên tự động làm mạch mở nếu nó không phản ánh tình trạng sức khỏe của dependency.
- **Thiết kế fallback theo nghiệp vụ:** kết quả dự phòng phải thể hiện rõ mức độ tin cậy và giới hạn của dữ liệu.
- **Giới hạn thời gian và mức đồng thời:** phối hợp timeout và bulkhead để kiểm soát tài nguyên bị chiếm dụng.
- **Kiểm soát retry:** tránh khuếch đại tải trong lúc dịch vụ đang phục hồi.
- **Theo dõi trạng thái và metrics:** kiểm tra hành vi thực tế trước khi điều chỉnh ngưỡng.
- **Kiểm thử tình huống lỗi:** mô phỏng timeout, lỗi kết nối, tỷ lệ lỗi tăng, dịch vụ phục hồi và fallback để hiểu hệ thống phản ứng ra sao.

Circuit Breaker phù hợp khi một dependency có thể thất bại độc lập và việc tiếp tục gọi nó có nguy cơ làm cạn tài nguyên của dịch vụ gọi. Nó không thay thế thiết kế hệ thống tốt, kiểm soát tải hay xử lý lỗi nghiệp vụ. Khi kết hợp trạng thái CLOSED/OPEN/HALF_OPEN, sliding window, timeout, bulkhead, fallback và quan sát vận hành, Spring Cloud CircuitBreaker cùng Resilience4j giúp ứng dụng giới hạn tác động của sự cố và phục hồi có kiểm soát.

