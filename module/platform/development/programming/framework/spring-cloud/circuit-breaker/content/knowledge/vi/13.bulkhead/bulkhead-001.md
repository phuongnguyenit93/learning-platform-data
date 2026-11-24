# Cô lập tài nguyên để một phụ thuộc lỗi không chiếm hết năng lực

Trong hệ thống microservices, một dịch vụ thường gọi nhiều dịch vụ phụ thuộc để hoàn thành một request. Nếu một dependency phản hồi rất chậm, các lời gọi đang chờ có thể chiếm hết thread, connection hoặc hàng đợi của dịch vụ gọi. Khi tài nguyên dùng chung bị chiếm hết, những chức năng không liên quan đến dependency đó cũng có thể ngừng phục vụ.

Bulkhead là mẫu thiết kế cô lập tài nguyên để giới hạn tác động của một thành phần gặp sự cố. Tên gọi xuất phát từ các vách ngăn trong thân tàu: khi một khoang bị ngập, vách ngăn giúp nước không lan sang toàn bộ con tàu. Trong phần mềm, mỗi dependency hoặc nhóm công việc được cấp một ngân sách tài nguyên riêng, chẳng hạn số lời gọi đồng thời, thread pool và hàng đợi.

Trong Spring Cloud CircuitBreaker, Resilience4j cung cấp các cơ chế Bulkhead để giới hạn concurrency. Bài học tập trung vào lý do cần cô lập, hai cách triển khai Semaphore Bulkhead và Thread Pool Bulkhead, cách cấu hình theo từng dependency và cách phối hợp Bulkhead với Circuit Breaker, timeout và fallback.

## 1. Vì sao Circuit Breaker chưa đủ?

Circuit Breaker theo dõi kết quả và độ trễ của lời gọi. Khi tỷ lệ lỗi hoặc lời gọi chậm vượt ngưỡng, nó có thể chuyển sang OPEN và từ chối lời gọi mới. Cơ chế này giúp ngừng gửi request đến dependency đã có dấu hiệu không khỏe.

Tuy nhiên, trước khi Circuit Breaker mở mạch, nhiều lời gọi vẫn có thể đang chờ. Một dependency chậm nhưng chưa tạo đủ mẫu để mở mạch vẫn có thể giữ thread và connection. Ngoài ra, một request có thể gọi nhiều dependency; sự cố ở một dependency không nên chiếm toàn bộ tài nguyên dành cho các dependency còn lại.

Bulkhead giải quyết một phần khác của bài toán:

- Giới hạn số lời gọi đang thực thi đồng thời đến một dependency.
- Có thể cô lập thread và hàng đợi riêng cho một nhóm lời gọi.
- Từ chối sớm khi ngân sách tài nguyên đã đầy.
- Giữ lại năng lực xử lý cho các dependency hoặc chức năng khác.

Ví dụ, Order gọi Inventory và Payment. Nếu Inventory chậm, một bulkhead giới hạn số lời gọi đến Inventory có thể ngăn các request tồn kho chiếm hết thread phục vụ Payment. Circuit Breaker có thể ngắt lời gọi Inventory khi nhận thấy tỷ lệ lỗi cao; Bulkhead giới hạn mức tiêu thụ tài nguyên trong lúc dependency chậm hoặc khi lưu lượng tăng đột biến.

## 2. Bulkhead hoạt động như thế nào?

Một ứng dụng có thể chia tài nguyên cho các dependency theo cách sau:

~~~text
                    Order Service
                          |
             +------------+------------+
             |                         |
             v                         v
       Bulkhead Inventory        Bulkhead Payment
       max 10 concurrent         max 8 concurrent
             |                         |
             v                         v
       Inventory Service          Payment Service
~~~

Mỗi bulkhead có giới hạn riêng. Khi Inventory không phản hồi, tối đa 10 lời gọi được phép chiếm ngân sách của bulkhead Inventory. Các lời gọi mới vượt giới hạn bị từ chối hoặc phải chờ trong thời gian cho phép. Bulkhead Payment vẫn có ngân sách riêng.

Bulkhead không sửa dependency và cũng không bảo đảm request thành công. Nó bảo vệ tài nguyên của caller bằng cách kiểm soát lượng công việc được phép đi vào một vùng thực thi.

Có hai chiến lược chính trong Resilience4j:

| Chiến lược | Cách cô lập | Đặc điểm |
| --- | --- | --- |
| Semaphore Bulkhead | Dùng semaphore để giới hạn số lời gọi đồng thời trên thread gọi hiện tại | Nhẹ, không tạo thread pool riêng; khi hết permit có thể từ chối hoặc chờ trong thời gian cấu hình |
| Thread Pool Bulkhead | Chạy công việc trong thread pool và hàng đợi riêng | Cô lập cả năng lực thực thi và hàng đợi; có chi phí quản lý thread và cần xử lý context propagation |

## 3. Semaphore Bulkhead

Semaphore Bulkhead giới hạn số lời gọi đồng thời bằng số permit. Mỗi lời gọi cần lấy một permit trước khi thực thi. Khi hoàn tất, permit được trả lại. Nếu không còn permit, lời gọi mới bị từ chối ngay hoặc chờ tối đa khoảng thời gian đã cấu hình.

Ví dụ, nếu maxConcurrentCalls là 10 thì tối đa 10 lời gọi Inventory được phép chạy cùng lúc qua bulkhead đó. Lời gọi thứ 11 không được thực thi cho đến khi có permit trở lại.

### 3.1. Cấu hình bằng Java

~~~java
import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.bulkhead.BulkheadConfig;

import java.time.Duration;

BulkheadConfig config = BulkheadConfig.custom()
    .maxConcurrentCalls(10)
    .maxWaitDuration(Duration.ZERO)
    .build();

Bulkhead inventoryBulkhead = Bulkhead.of("inventory", config);

InventoryResponse response = inventoryBulkhead.executeSupplier(
    () -> inventoryClient.getInventory("SKU-001")
);
~~~

Cấu hình trên cho phép tối đa 10 lời gọi đồng thời. maxWaitDuration bằng 0 nghĩa là không chờ permit; khi hết permit, lời gọi bị từ chối nhanh. Với một API cần thời gian chờ rất ngắn để chờ slot được giải phóng, có thể đặt maxWaitDuration nhỏ, nhưng phải nằm trong latency budget của request tổng thể.

Khi không lấy được permit, Resilience4j phát sinh BulkheadFullException. Ứng dụng có thể bắt lỗi này để trả response phù hợp, ví dụ thông báo dịch vụ đang quá tải hoặc kết quả dự phòng nếu nghiệp vụ cho phép.

### 3.2. Cấu hình bằng application.yml

Với Resilience4j Spring Boot integration, có thể khai báo bulkhead theo tên instance:

~~~yaml
resilience4j:
  bulkhead:
    instances:
      inventory:
        maxConcurrentCalls: 10
        maxWaitDuration: 0

      payment:
        maxConcurrentCalls: 8
        maxWaitDuration: 20ms
~~~

Ở ví dụ này, Inventory không chờ permit khi đã đạt giới hạn; Payment được phép chờ tối đa 20 ms. Giá trị cần được chọn theo thời gian phản hồi mục tiêu và mức độ chịu tải của từng dependency.

Các thuộc tính chính:

- maxConcurrentCalls: số lời gọi đồng thời tối đa.
- maxWaitDuration: thời gian tối đa chờ lấy permit khi không còn permit khả dụng.

Semaphore Bulkhead không tạo thread pool. Supplier được thực thi trên thread gọi. Vì vậy, nó phù hợp khi muốn giới hạn concurrency mà vẫn giữ mô hình thực thi hiện tại, đồng thời tránh chi phí tạo và quản lý pool riêng.

## 4. Thread Pool Bulkhead

Thread Pool Bulkhead tạo một vùng thực thi riêng với thread pool và hàng đợi có giới hạn. Lời gọi được gửi vào pool thay vì chạy trực tiếp trên thread gọi. Điều này giúp giới hạn số thread dành cho dependency và tránh để các lời gọi chậm chiếm toàn bộ thread xử lý request.

Ví dụ, một bulkhead Inventory có 4 core thread, tối đa 8 thread và hàng đợi 20 tác vụ. Khi 8 thread đều bận, tối đa 20 tác vụ tiếp theo có thể chờ trong queue. Khi thread và queue đều đầy, tác vụ mới bị từ chối.

### 4.1. Cấu hình bằng Java

~~~java
import io.github.resilience4j.bulkhead.ThreadPoolBulkhead;
import io.github.resilience4j.bulkhead.ThreadPoolBulkheadConfig;

import java.time.Duration;
import java.util.concurrent.CompletionStage;

ThreadPoolBulkheadConfig config = ThreadPoolBulkheadConfig.custom()
    .coreThreadPoolSize(4)
    .maxThreadPoolSize(8)
    .queueCapacity(20)
    .keepAliveDuration(Duration.ofSeconds(20))
    .build();

ThreadPoolBulkhead inventoryBulkhead =
    ThreadPoolBulkhead.of("inventory", config);

CompletionStage<InventoryResponse> result =
    inventoryBulkhead.executeSupplier(
        () -> inventoryClient.getInventory("SKU-001")
    );

result.whenComplete((response, error) -> {
    if (error != null) {
        // Ghi nhận lỗi hoặc chuyển sang xử lý fallback phù hợp.
        log.warn("Inventory task failed", error);
    }
});
~~~

Thread Pool Bulkhead trả về CompletionStage vì công việc được thực thi bất đồng bộ trên pool. Không nên gọi join() hoặc get() ngay trên thread nhận HTTP request nếu mục tiêu là giữ luồng xử lý không bị chặn; thao tác đó sẽ biến lợi ích bất đồng bộ thành một lần chờ đồng bộ.

Các tham số chính:

- coreThreadPoolSize: số thread cơ sở được duy trì.
- maxThreadPoolSize: số thread tối đa.
- queueCapacity: số tác vụ tối đa có thể chờ trong hàng đợi.
- keepAliveDuration: thời gian thread dư có thể tồn tại khi không có công việc, tùy cách pool quản lý thread.

Thread pool và queue phải có giới hạn. Một hàng đợi quá lớn có thể giữ quá nhiều request trong thời gian dài, làm tăng độ trễ và tiêu thụ bộ nhớ. Từ chối sớm thường tốt hơn việc xếp hàng vô hạn cho một dependency đang chậm.

### 4.2. Cấu hình bằng application.yml

~~~yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      inventory:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 20
        keepAliveDuration: 20ms
~~~

Cấu hình thread pool bulkhead độc lập với cấu hình semaphore bulkhead. Hãy chọn chiến lược phù hợp với mô hình thực thi của ứng dụng. Không nên nghĩ rằng cấu hình cả hai nhóm instance với cùng tên sẽ tự động tạo hai lớp cô lập nối tiếp; cần hiểu rõ provider nào đang được Spring Cloud CircuitBreaker sử dụng.

## 5. Chọn Semaphore hay Thread Pool Bulkhead?

Hai chiến lược đều giới hạn công việc, nhưng cách chúng sử dụng thread khác nhau.

| Tiêu chí | Semaphore Bulkhead | Thread Pool Bulkhead |
| --- | --- | --- |
| Thread thực thi | Thread gọi hiện tại | Thread thuộc pool riêng |
| Cô lập thread | Không | Có |
| Giới hạn concurrency | Có | Có, qua số thread và queue |
| Hàng đợi riêng | Không có queue công việc riêng | Có queue hữu hạn |
| Chi phí tài nguyên | Thấp hơn, ít thành phần hơn | Cao hơn do quản lý pool và queue |
| Context ThreadLocal | Thường giữ trên cùng thread | Cần context propagation |
| Mô hình trả kết quả | Đồng bộ | Bất đồng bộ qua CompletionStage |
| Phù hợp | Lời gọi đồng bộ, muốn giới hạn số request đang chạy | Cần pool riêng để cô lập thread hoặc tích hợp công việc bất đồng bộ |

Semaphore phù hợp khi ứng dụng đã có thread pool phục vụ request và chỉ cần giới hạn số lời gọi đến dependency. Nó không bảo vệ thread gọi khỏi việc bị giữ lâu bởi HTTP request; timeout của HTTP client vẫn cần thiết.

Thread Pool Bulkhead phù hợp khi cần tách năng lực thực thi của dependency khỏi thread nhận request. Đổi lại, ứng dụng phải xử lý kết quả bất đồng bộ, truyền context và quản lý vòng đời pool.

Không có một chiến lược tốt nhất cho mọi dịch vụ. Hãy chọn dựa trên latency, concurrency, cách HTTP client thực thi và yêu cầu bảo toàn ngữ cảnh của request.

## 6. Tích hợp Bulkhead trong Spring Cloud CircuitBreaker

Spring Cloud CircuitBreaker cung cấp abstraction để gọi Circuit Breaker. Khi dùng Resilience4j provider, bulkhead integration có thể được kích hoạt để giới hạn lời gọi theo tên Circuit Breaker.

Starter Resilience4j của Spring Cloud CircuitBreaker đưa các module Bulkhead và TimeLimiter cần thiết vào classpath. Theo cấu hình mặc định, nếu Resilience4j Bulkhead có mặt, Spring Cloud CircuitBreaker sử dụng FixedThreadPoolBulkhead. Có thể chọn Semaphore Bulkhead làm mặc định bằng thuộc tính:

~~~yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        enableSemaphoreDefaultBulkhead: true
~~~

Hãy xác nhận thuộc tính này với phiên bản Spring Cloud đang sử dụng. Khi bật, lời gọi mặc định dùng semaphore bulkhead thay vì fixed thread pool bulkhead.

Một service có thể tiếp tục sử dụng CircuitBreakerFactory:

~~~java
import org.springframework.cloud.client.circuitbreaker.CircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryGateway {

    private final CircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final InventoryClient inventoryClient;

    public InventoryGateway(
            CircuitBreakerFactory<?, ?> circuitBreakerFactory,
            InventoryClient inventoryClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryClient = inventoryClient;
    }

    public InventoryResponse getInventory(String sku) {
        return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.getInventory(sku),
            error -> InventoryResponse.unavailable(sku)
        );
    }
}
~~~

Tên inventory là định danh dùng để liên kết lời gọi với cấu hình instance. Cấu hình Bulkhead theo tên đó trong application.yml. Khi bulkhead đầy, lời gọi có thể bị từ chối và fallback nhận lỗi nếu provider đưa lỗi từ chối qua đường xử lý fallback. Cần kiểm tra hành vi cụ thể với phiên bản Spring Cloud CircuitBreaker và loại bulkhead đã chọn.

Ví dụ cấu hình semaphore cho lời gọi trên:

~~~yaml
spring:
  cloud:
    circuitbreaker:
      resilience4j:
        enableSemaphoreDefaultBulkhead: true

resilience4j:
  bulkhead:
    instances:
      inventory:
        maxConcurrentCalls: 10
        maxWaitDuration: 0
  circuitbreaker:
    instances:
      inventory:
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
~~~

Nếu không bật semaphore default, cấu hình thread pool bulkhead có thể được dùng thay thế:

~~~yaml
resilience4j:
  thread-pool-bulkhead:
    instances:
      inventory:
        coreThreadPoolSize: 4
        maxThreadPoolSize: 8
        queueCapacity: 20
        keepAliveDuration: 20ms
~~~

Hai đoạn cấu hình trên minh họa hai lựa chọn. Khi triển khai, hãy xác nhận bulkhead provider thực sự đang được dùng, tên instance khớp với tên Circuit Breaker và các thuộc tính cấu hình được bind đúng.

## 7. Chọn giới hạn dựa trên năng lực thực tế

Không nên chọn maxConcurrentCalls hoặc queueCapacity theo cảm tính. Một giới hạn quá thấp làm từ chối request dù dependency vẫn còn khả năng phục vụ. Một giới hạn quá cao làm mất tác dụng cô lập và có thể khiến dependency quá tải.

Có thể bắt đầu bằng định luật Little để ước lượng số lời gọi đồng thời trung bình:

\[
L = \lambda \times W
\]

Trong đó:

- L là số request trung bình đang ở trong hệ thống.
- λ là tốc độ request đến, tính bằng request mỗi giây.
- W là thời gian xử lý trung bình, tính bằng giây.

Ví dụ, Inventory nhận 40 request mỗi giây và thời gian xử lý trung bình là 0,2 giây:

\[
L = 40 \times 0.2 = 8
\]

Nghĩa là trung bình có khoảng 8 lời gọi đang xử lý đồng thời. Đây chỉ là giá trị tham khảo; khi chọn giới hạn cần tính thêm burst traffic, độ trễ ở percentile cao, giới hạn connection pool và năng lực thực tế của Inventory.

Một quy trình chọn giới hạn có thể gồm:

1. Đo tốc độ request và thời gian xử lý của dependency trong điều kiện tải bình thường.
2. Xác định mức concurrency tối đa mà dependency có thể phục vụ ổn định.
3. Chọn giới hạn ban đầu thấp hơn hoặc bằng ngân sách đã xác nhận.
4. Chọn queue hữu hạn nếu dùng thread pool, dựa trên latency budget.
5. Tạo tải tăng dần và quan sát tỷ lệ từ chối, độ trễ và tài nguyên.
6. Điều chỉnh từng tham số rồi đo lại.

Đối với semaphore, maxWaitDuration nên ngắn hơn phần thời gian còn lại trong latency budget. Nếu caller chỉ còn 100 ms trước deadline, không nên để bulkhead chờ permit trong 500 ms.

Đối với thread pool, queueCapacity cần đủ để hấp thụ burst ngắn nhưng không được lớn đến mức request chờ quá lâu. Queue không thay thế khả năng xử lý; nếu tốc độ đến liên tục cao hơn tốc độ hoàn tất, queue cuối cùng vẫn đầy.

## 8. Phối hợp Bulkhead, Circuit Breaker và Timeout

Ba cơ chế giải quyết ba giới hạn khác nhau:

| Cơ chế | Câu hỏi cần trả lời |
| --- | --- |
| Bulkhead | Có bao nhiêu lời gọi được phép chiếm tài nguyên cùng lúc? |
| Circuit Breaker | Khi dependency có dấu hiệu lỗi, có nên tiếp tục gửi lời gọi không? |
| Timeout / TimeLimiter | Một lời gọi được phép chờ tối đa bao lâu? |

Ví dụ, Order gọi Inventory với các giới hạn sau:

- Bulkhead cho tối đa 10 lời gọi đồng thời.
- HTTP client timeout sau 800 ms.
- Circuit Breaker mở mạch nếu tỷ lệ lỗi hoặc lời gọi chậm vượt ngưỡng.

Khi Inventory chậm, timeout giải phóng các lời gọi đã vượt giới hạn chờ. Bulkhead giới hạn số lời gọi đang chiếm tài nguyên trong khi chờ. Circuit Breaker quan sát các lỗi hoặc lời gọi chậm và có thể ngắt các lời gọi mới trong một khoảng thời gian.

Cần tránh để BulkheadFullException bị tính như lỗi của dependency nếu mục tiêu Circuit Breaker là đánh giá sức khỏe của Inventory. Bulkhead đầy có thể phản ánh caller đã hết ngân sách concurrency, trong khi Inventory chưa chắc đang lỗi. Có thể cấu hình Circuit Breaker bỏ qua loại exception này nếu phù hợp với cách tích hợp và phân loại lỗi của ứng dụng. Nếu muốn cảnh báo quá tải cục bộ, hãy theo dõi metric từ chối của Bulkhead riêng.

Timeout cũng cần được đặt hợp lý. Timeout của HTTP client giới hạn thời gian chờ ở tầng mạng. TimeLimiter giới hạn thời gian hoàn tất của một tác vụ bất đồng bộ. Chúng có thể phối hợp nhưng không phải lúc nào cũng hủy được công việc đang chạy ở dependency; cần kiểm tra khả năng cancellation của HTTP client và executor.

## 9. Context propagation khi dùng Thread Pool Bulkhead

Thread Pool Bulkhead thực thi supplier trên thread riêng. MDC và SecurityContext thường dựa trên ThreadLocal nên không tự động có mặt trong thread pool.

Nếu log cần correlation ID, hoặc lời gọi cần danh tính xác thực, cần cấu hình context propagation phù hợp. Có thể dùng Micrometer Context Propagation và các cơ chế tích hợp của Spring, hoặc truyền các giá trị cần thiết qua tham số một cách tường minh.

Với SecurityContext, nếu executor do ứng dụng quản lý, có thể dùng các wrapper của Spring Security như DelegatingSecurityContextExecutor. Nếu Resilience4j quản lý thread pool, cần xác định hook propagation mà phiên bản tích hợp hỗ trợ. Không nên giả định một executor wrapper tự động bọc được pool nội bộ của thư viện.

Không nên dùng InheritableThreadLocal như giải pháp chung cho pool tái sử dụng thread. Context có thể tồn tại ngoài vòng đời request và gây lẫn danh tính giữa các tác vụ. Hãy luôn dọn context sau khi task hoàn tất.

Semaphore Bulkhead không chuyển thread nên các ThreadLocal hiện tại thường vẫn có thể được đọc trong supplier. Tuy nhiên, vẫn cần bảo đảm filter và middleware dọn context đúng sau request.

## 10. Quan sát Bulkhead

Một Bulkhead được cấu hình đúng cần được giám sát. Các chỉ số hữu ích gồm:

- Số lời gọi đang sử dụng permit hoặc thread.
- Số permit còn trống.
- Số lời gọi bị từ chối vì bulkhead đầy.
- Số thread đang hoạt động và kích thước queue.
- Thời gian chờ trong queue hoặc chờ permit.
- Độ trễ thực thi của dependency.
- Tỷ lệ fallback do bulkhead từ chối hoặc do dependency lỗi.

Resilience4j tích hợp Micrometer để xuất metrics. Spring Boot Actuator có thể công bố endpoint metrics nếu dependency và cấu hình exposure đã được bật. Tên metric và tag cụ thể phụ thuộc phiên bản, vì vậy hãy truy vấn danh sách metrics thực tế thay vì giả định tên cố định.

Dashboard nên phân biệt lỗi dependency với từ chối do bulkhead. Nếu Bulkhead thường xuyên đầy nhưng Circuit Breaker vẫn CLOSED, có thể caller đang nhận lưu lượng vượt ngân sách concurrency. Nếu tỷ lệ lỗi dependency tăng đồng thời với bulkhead rejection, cần kiểm tra latency và sức khỏe của provider.

Cảnh báo nên dựa trên xu hướng và ngưỡng vận hành, ví dụ tỷ lệ rejection tăng kéo dài hoặc queue thường xuyên gần đầy. Một vài lần từ chối trong đợt burst ngắn không nhất thiết có nghĩa cấu hình sai.

## 11. Thực hành mô phỏng bulkhead đầy

Có thể thử nghiệm với một endpoint giả lập phản hồi chậm và một bulkhead giới hạn nhỏ:

- Cấu hình maxConcurrentCalls bằng 2.
- Cho provider mất 3 giây để hoàn thành mỗi request.
- Gửi đồng thời 5 request từ client.
- Quan sát hai request được phép chạy và các request vượt giới hạn bị từ chối hoặc chờ theo maxWaitDuration.
- Gửi request đến một dependency khác để xác nhận ngân sách của dependency đó không bị bulkhead Inventory chiếm dụng.

Với Thread Pool Bulkhead, có thể đặt coreThreadPoolSize và maxThreadPoolSize bằng 2, queueCapacity bằng 1. Khi hai thread đang bận và một tác vụ nằm trong queue, tác vụ tiếp theo có thể bị từ chối. Kết quả chính xác còn phụ thuộc thời điểm gửi request và cách pool nhận task.

Trong quá trình thử, ghi lại:

1. Thời điểm gửi từng request.
2. Số request được provider tiếp nhận.
3. Số request bị từ chối ở caller.
4. Thời gian phản hồi của request thành công và request fallback.
5. Metrics concurrency, queue và rejection.

Sau đó tăng giới hạn từ 2 lên 4 và lặp lại phép thử. So sánh tỷ lệ từ chối, độ trễ và số request đang chạy để thấy tác động của cấu hình. Không nên chỉ nhìn vào số request thành công; cần quan sát cả độ trễ và tài nguyên của dependency.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Request bị từ chối dù dependency vẫn khỏe | maxConcurrentCalls quá thấp hoặc có burst traffic | Đo concurrency và điều chỉnh theo latency budget |
| Thread caller vẫn bị giữ lâu | Semaphore chỉ giới hạn concurrency, không giới hạn thời gian chờ | Cấu hình timeout cho HTTP client |
| Queue tăng liên tục | Tốc độ đến cao hơn tốc độ xử lý hoặc queueCapacity quá lớn | Giảm queue, giới hạn tải và kiểm tra dependency |
| MDC hoặc SecurityContext bị mất | Thread Pool Bulkhead chuyển sang thread khác | Cấu hình context propagation hoặc truyền context tường minh |
| Circuit Breaker mở do bulkhead đầy | BulkheadFullException bị tính như lỗi dependency | Phân loại exception và cân nhắc ignore exception phù hợp |
| Không thấy metrics | Chưa bật Micrometer hoặc Actuator endpoint chưa được expose | Kiểm tra dependency, registry và endpoint metrics |
| Cấu hình không áp dụng | Tên instance trong code và YAML không khớp hoặc đang dùng loại bulkhead khác | Kiểm tra tên instance và default bulkhead provider |
| Nhiều request chờ quá lâu | maxWaitDuration hoặc queueCapacity vượt latency budget | Giảm thời gian chờ và đặt queue hữu hạn |

## 13. Nguyên tắc thiết kế

- Tạo ngân sách riêng cho từng dependency quan trọng.
- Chọn semaphore khi chỉ cần giới hạn concurrency trên thread gọi.
- Chọn thread pool khi cần cô lập thread và chấp nhận mô hình bất đồng bộ.
- Giới hạn queue để tránh tích tụ request và tiêu thụ bộ nhớ không kiểm soát.
- Đặt thời gian chờ permit và timeout trong latency budget tổng thể.
- Phân biệt lỗi do dependency với lỗi từ chối do bulkhead đầy.
- Kiểm tra cách Bulkhead kết hợp với Circuit Breaker và fallback trong đúng phiên bản Spring Cloud.
- Truyền MDC, trace context và SecurityContext khi công việc chuyển sang thread pool.
- Theo dõi concurrency, rejection, queue và latency để điều chỉnh cấu hình dựa trên dữ liệu.
- Kiểm thử tải tăng dần và tình huống dependency chậm trước khi triển khai production.

Bulkhead giúp một dependency chậm hoặc quá tải không chiếm hết năng lực của dịch vụ gọi. Semaphore Bulkhead giới hạn số lời gọi đang chạy trên thread hiện tại; Thread Pool Bulkhead cô lập thêm thread và queue riêng. Khi kết hợp với Circuit Breaker, timeout và fallback, ứng dụng Spring Cloud có thể kiểm soát cả số lượng công việc, thời gian chờ và phản ứng khi dependency gặp sự cố.

## Tài liệu tham khảo

- [Resilience4j Bulkhead](https://resilience4j.readme.io/docs/bulkhead)
- [Spring Cloud CircuitBreaker reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
- [Spring Cloud CircuitBreaker — Resilience4j](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html)
- [Resilience4j Micrometer metrics](https://resilience4j.readme.io/docs/micrometer)

