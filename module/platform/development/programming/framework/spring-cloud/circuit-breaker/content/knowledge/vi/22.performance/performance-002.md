# Tính an toàn luồng và phạm vi đồng bộ hóa của Resilience4j

Một ứng dụng Spring thường xử lý nhiều request cùng lúc trên nhiều thread. Nếu các request cùng gọi Inventory hoặc Payment qua một Circuit Breaker, nhiều thread sẽ cùng đọc trạng thái và cập nhật kết quả của một instance Resilience4j. Vì vậy, cần hiểu phần nào của Resilience4j đã được thiết kế an toàn luồng, phần nào được đồng bộ hóa và phần nào vẫn thuộc trách nhiệm của mã ứng dụng.

Circuit Breaker của Resilience4j được thiết kế để nhiều thread cùng sử dụng một instance. Tuy nhiên, điều đó không có nghĩa Circuit Breaker khóa toàn bộ lời gọi từ xa hoặc tự giới hạn số request đang chạy. Các lời gọi đã được cho phép có thể thực thi đồng thời; phần ghi nhận kết quả và chuyển trạng thái được quản lý an toàn bởi cơ chế nội bộ. Nếu cần giới hạn concurrency, ứng dụng phải kết hợp Bulkhead.

Bài học trình bày phạm vi thread safety và synchronization của Resilience4j trong ứng dụng Spring Cloud CircuitBreaker, các tình huống cạnh tranh khi nhiều request đến cùng lúc, cách viết service và callback an toàn luồng, cũng như cách xử lý context khi công việc chuyển sang thread khác.

## 1. Vì sao thread safety quan trọng?

Giả sử một service Spring Boot có một bean InventoryGateway và bean này được tạo một lần khi ứng dụng khởi động. Nhiều request HTTP có thể đồng thời gọi cùng phương thức getInventory. Nếu Circuit Breaker được lấy từ registry theo tên inventory, các request đó thường dùng chung một instance Circuit Breaker.

Luồng thực thi có thể như sau:

~~~text
HTTP request A ----\
HTTP request B -----+--> InventoryGateway (Spring singleton)
HTTP request C ----/             |
                                  v
                         CircuitBreaker inventory
                                  |
                    +-------------+-------------+
                    |             |             |
                    v             v             v
                 Thread A      Thread B      Thread C
                    |             |             |
                    +-------------+-------------+
                                  |
                                  v
                           Inventory service
~~~

Các thread cùng truy cập một instance có thể đồng thời:

- Kiểm tra Circuit Breaker có cho phép lời gọi mới hay không.
- Bắt đầu gọi dependency.
- Ghi nhận kết quả thành công, thất bại hoặc lời gọi chậm.
- Cập nhật sliding window và metrics.
- Phát sinh sự kiện chuyển trạng thái.

Nếu các thao tác này không được quản lý đồng bộ, số liệu có thể sai hoặc trạng thái bị cập nhật không nhất quán. Resilience4j cung cấp các cơ chế nội bộ để xử lý những truy cập đồng thời đó. Mã ứng dụng vẫn phải bảo vệ dữ liệu mutable do chính nó quản lý.

## 2. Circuit Breaker an toàn luồng nhưng không tuần tự hóa lời gọi

CircuitBreaker của Resilience4j được thiết kế thread-safe. Nhiều thread có thể dùng cùng một instance mà không cần tạo một Circuit Breaker riêng cho mỗi request.

Điều này không có nghĩa mọi lời gọi được thực thi lần lượt. Circuit Breaker không khóa supplier hoặc function trong suốt thời gian gọi dependency. Khi trạng thái cho phép, nhiều thread có thể cùng được cấp quyền và thực thi phần gọi từ xa đồng thời.

Ví dụ:

~~~java
CircuitBreaker inventoryBreaker =
    circuitBreakerRegistry.circuitBreaker("inventory");

public InventoryResponse getInventory(String sku) {
    return inventoryBreaker.executeSupplier(
        () -> inventoryClient.getInventory(sku)
    );
}
~~~

Nếu 20 request gọi phương thức trên cùng lúc và Circuit Breaker đang CLOSED, nhiều lời gọi có thể cùng đi đến Inventory. Circuit Breaker ghi nhận kết quả và điều khiển trạng thái; nó không mặc định giới hạn số lời gọi đang chạy.

Cần phân biệt:

- **Thread safety:** nhiều thread có thể dùng chung đối tượng mà không làm hỏng trạng thái nội bộ.
- **Synchronization:** một số thao tác chia sẻ dữ liệu được bảo vệ để cập nhật nhất quán.
- **Concurrency limit:** số lời gọi được phép chạy đồng thời. Đây là trách nhiệm của Bulkhead hoặc cơ chế giới hạn tải khác.
- **Serialization:** buộc mọi lời gọi chạy lần lượt. Circuit Breaker không cung cấp hành vi này.

Nếu muốn tối đa 10 lời gọi Inventory đang chạy đồng thời, hãy cấu hình Bulkhead với giới hạn phù hợp. Không nên dựa vào Circuit Breaker để làm nhiệm vụ giới hạn concurrency.

## 3. Phạm vi đồng bộ hóa bên trong Circuit Breaker

Circuit Breaker phải quản lý ít nhất hai nhóm trạng thái: trạng thái hiện tại như CLOSED, OPEN, HALF_OPEN và dữ liệu thống kê trong sliding window.

Ở mức khái niệm:

- State machine phải bảo đảm các thread quan sát được trạng thái nhất quán và chuyển trạng thái theo quy tắc.
- Sliding window phải cập nhật tổng số lời gọi, số lỗi và số lời gọi chậm mà không làm mất hoặc nhân đôi kết quả do cạnh tranh giữa các thread.
- Metrics phải phản ánh các kết quả đã được ghi nhận.
- Việc gọi supplier đến dependency được thực thi ngoài vùng đồng bộ hóa của state/window, để một lời gọi mạng chậm không giữ khóa của Circuit Breaker trong suốt thời gian chờ.

Resilience4j dùng các cơ chế đồng bộ và cấu trúc dữ liệu an toàn luồng cho state machine và sliding window. Chi tiết triển khai có thể thay đổi theo phiên bản, vì vậy không nên phụ thuộc vào một loại lock hoặc cấu trúc nội bộ cụ thể trong mã nghiệp vụ.

Điều quan trọng ở góc nhìn ứng dụng là: phần ghi nhận kết quả được bảo vệ, còn công việc nghiệp vụ vẫn có thể chạy song song. Circuit Breaker không biến một phương thức service thành critical section duy nhất.

~~~text
Thread A                  CircuitBreaker                 Thread B
   |                            |                           |
   |---- kiểm tra quyền ------->|<------ kiểm tra quyền ----|
   |<--- được phép -------------|------------- được phép -->|
   |                            |                           |
   |---- gọi Inventory          |          gọi Inventory ---|
   |                            |                           |
   |---- ghi kết quả ---------->|<--------- ghi kết quả ----|
   |                            |                           |
   |                     cập nhật window/state              |
~~~

Hai lời gọi có thể đang chạy cùng lúc. Khi một kết quả làm Circuit Breaker chuyển sang OPEN, các lời gọi mới sau thời điểm chuyển trạng thái sẽ bị từ chối. Những lời gọi đã được cấp quyền trước đó không tự động bị hủy.

## 4. Lời gọi đang thực thi khi Circuit Breaker chuyển OPEN

Một tình huống thường gặp là nhiều request đã được cho phép trong trạng thái CLOSED, sau đó một số request thất bại và làm Circuit Breaker chuyển sang OPEN.

Ví dụ:

1. Request A, B và C được cấp quyền khi Circuit Breaker đang CLOSED.
2. Cả ba bắt đầu gọi Inventory.
3. A và B trả lỗi, kết quả làm tỷ lệ lỗi vượt ngưỡng.
4. Circuit Breaker chuyển sang OPEN.
5. Request D đến sau đó bị từ chối.
6. Request C đã bắt đầu trước khi mạch mở vẫn có thể tiếp tục đến khi hoàn tất hoặc timeout.

Circuit Breaker không có khả năng tự hủy một HTTP request đang chạy chỉ vì state chuyển sang OPEN. Việc dừng lời gọi đang thực thi thuộc về timeout, cancellation và HTTP client. Vì vậy, Circuit Breaker cần được phối hợp với timeout để giới hạn thời gian tài nguyên bị giữ.

Điều này cũng giải thích vì sao sau khi Circuit Breaker OPEN, log của dependency vẫn có thể xuất hiện một số request đã được gửi trước thời điểm chuyển trạng thái. Không nên kết luận rằng Circuit Breaker không hoạt động chỉ vì một lời gọi đang bay (in-flight call) vẫn hoàn tất sau khi mạch mở.

## 5. HALF_OPEN và các lời gọi thăm dò đồng thời

Trong HALF_OPEN, Circuit Breaker chỉ cho phép số lượng lời gọi thăm dò được cấu hình. Thuộc tính permittedNumberOfCallsInHalfOpenState giới hạn số lời gọi được phép trong giai đoạn này.

Ví dụ:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
        automaticTransitionFromOpenToHalfOpenEnabled: true
~~~

Sau thời gian OPEN, tối đa ba lời gọi thăm dò được phép theo cấu hình. Các request khác trong thời gian này có thể bị từ chối cho đến khi Circuit Breaker quyết định chuyển về CLOSED hoặc quay lại OPEN.

Khi nhiều thread đồng thời yêu cầu quyền trong HALF_OPEN, state machine phải bảo đảm không cấp vượt số permit đã cấu hình. Ứng dụng không cần tự đồng bộ hóa để đếm probe nếu chỉ sử dụng API Circuit Breaker chính thức.

Tuy nhiên, cần lưu ý rằng ba probe có thể chạy đồng thời. Nếu dependency chỉ chịu được một request thăm dò tại một thời điểm, hãy giảm permittedNumberOfCallsInHalfOpenState xuống 1 hoặc kết hợp Bulkhead phù hợp.

Trong hệ thống có nhiều replica, mỗi replica thường có Circuit Breaker instance và state riêng. Nếu các replica cùng chuyển HALF_OPEN gần như đồng thời, tổng số probe gửi đến dependency có thể lớn hơn giá trị cấu hình trên một instance. Hãy tính tổng tải thăm dò trên toàn hệ thống.

## 6. Dùng chung instance trong Spring singleton bean

Spring thường quản lý service bean theo scope singleton. Một instance service được nhiều request sử dụng đồng thời. Đây là mô hình bình thường và tương thích với Resilience4j nếu service không giữ dữ liệu mutable theo request trong field dùng chung.

Ví dụ phù hợp:

~~~java
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

Các dependency được inject vào constructor và không thay đổi sau khi bean được tạo. Mỗi request truyền SKU riêng qua tham số. Circuit Breaker instance được quản lý theo tên, không cần tạo mới ở mỗi lần gọi.

Ví dụ không an toàn:

~~~java
@Service
public class UnsafeInventoryGateway {

    private String currentSku;

    public InventoryResponse getInventory(String sku) {
        currentSku = sku;
        return inventoryClient.getInventory(currentSku);
    }
}
~~~

Nếu hai thread gọi cùng lúc, thread A có thể gán currentSku bằng SKU-A, thread B ghi đè thành SKU-B trước khi A sử dụng giá trị. Kết quả có thể gọi nhầm SKU.

Hãy tránh lưu request-specific data trong field của singleton bean. Truyền dữ liệu qua tham số phương thức hoặc dùng một execution context có vòng đời phù hợp.

## 7. Những đối tượng nào cần được bảo vệ ở phía ứng dụng?

Thread safety của Circuit Breaker không tự lan sang các đối tượng được supplier, fallback hoặc listener sử dụng.

| Thành phần | Rủi ro khi nhiều thread cùng truy cập | Cách thiết kế |
| --- | --- | --- |
| CircuitBreaker instance | Nhiều thread cùng đọc state và ghi kết quả | Dùng API Resilience4j; instance được thiết kế để chia sẻ |
| Service singleton | Field mutable bị nhiều request ghi đồng thời | Ưu tiên field final và dữ liệu bất biến |
| HTTP client | Dùng chung client không phù hợp hoặc thay đổi cấu hình trong lúc gọi | Dùng client do framework quản lý và cấu hình trước khi phục vụ request |
| Cache hoặc map nghiệp vụ | Race condition khi đọc/ghi | Dùng ConcurrentHashMap, cache có hỗ trợ concurrency hoặc lock phù hợp |
| Bộ đếm tùy chỉnh | Mất cập nhật khi nhiều thread tăng cùng lúc | Dùng AtomicLong, LongAdder hoặc Micrometer Counter |
| Fallback callback | Nhiều request cùng chạy fallback | Không dùng state mutable dùng chung nếu chưa đồng bộ |
| Event listener | Callback chậm làm tăng latency của luồng phát sự kiện | Giữ listener ngắn, tránh I/O blocking |
| Request context | MDC hoặc SecurityContext bị lẫn khi đổi thread | Dùng context propagation và cleanup đúng vòng đời |

Không nên dùng synchronized trên toàn bộ phương thức service chỉ để bảo vệ một biến nhỏ. Điều đó có thể tuần tự hóa các request và làm giảm throughput. Hãy chọn cấu trúc dữ liệu thread-safe hoặc đồng bộ hóa đúng đoạn cập nhật cần bảo vệ.

## 8. Thread safety của Retry và các chính sách khác

Resilience4j thường quản lý các instance policy theo registry để nhiều request có thể dùng chung cấu hình và metrics. Retry, RateLimiter và Bulkhead cũng được thiết kế để sử dụng trong môi trường đồng thời thông qua API của thư viện.

Tuy nhiên, cần phân biệt instance policy với dữ liệu theo từng lần thực thi:

- Cấu hình Retry có thể được dùng chung giữa các request.
- Mỗi lần thực thi Retry có chuỗi attempt và kết quả riêng.
- Một request retry không nên dùng chung biến đếm attempt mutable với request khác.
- Bulkhead quản lý permit hoặc pool theo instance.
- RateLimiter quản lý quyền theo chu kỳ và cấu hình của instance.
- Callback do ứng dụng cung cấp vẫn phải an toàn nếu nhiều request gọi đồng thời.

Ví dụ không nên dùng một biến instance để đếm attempt:

~~~java
@Service
public class UnsafeRetryService {

    private int attempt;

    public InventoryResponse load() {
        attempt = 0;
        // Retry callback tăng attempt và gọi dependency.
        return performCall();
    }

    private InventoryResponse performCall() {
        attempt++;
        return inventoryClient.getInventory();
    }
}
~~~

Hai request đồng thời có thể ghi đè và tăng chung biến attempt. Nếu cần attempt number, hãy lưu nó trong biến cục bộ thuộc execution hoặc dùng metadata riêng cho từng lần thực thi.

Không nên giả định mọi object tùy chỉnh được truyền vào Retry, Circuit Breaker hoặc Bulkhead đều thread-safe chỉ vì policy của Resilience4j thread-safe. Supplier, fallback và listener có thể được gọi đồng thời.

## 9. Circuit Breaker không thay thế Bulkhead

Circuit Breaker kiểm soát việc có cho phép lời gọi mới dựa trên kết quả thống kê gần đây hay không. Bulkhead kiểm soát số lời gọi được chạy đồng thời hoặc tài nguyên thực thi dành cho một dependency.

Hai cơ chế giải quyết các vấn đề khác nhau:

| Câu hỏi | Cơ chế |
| --- | --- |
| Dependency đang lỗi, có nên tiếp tục gọi? | Circuit Breaker |
| Có bao nhiêu lời gọi được chạy đồng thời? | Bulkhead |
| Một lời gọi được phép chờ tối đa bao lâu? | HTTP client timeout hoặc TimeLimiter |
| Có nên thử lại lỗi transient? | Retry |

Ví dụ dùng Semaphore Bulkhead:

~~~java
BulkheadConfig bulkheadConfig = BulkheadConfig.custom()
    .maxConcurrentCalls(10)
    .maxWaitDuration(Duration.ZERO)
    .build();

Bulkhead inventoryBulkhead =
    Bulkhead.of("inventory", bulkheadConfig);

Supplier<InventoryResponse> protectedCall =
    Bulkhead.decorateSupplier(
        inventoryBulkhead,
        () -> inventoryClient.getInventory("SKU-001")
    );

InventoryResponse response = protectedCall.get();
~~~

Tối đa 10 lời gọi được phép đi qua bulkhead cùng lúc. Lời gọi vượt giới hạn bị từ chối ngay do maxWaitDuration bằng 0. Circuit Breaker có thể được lồng với Bulkhead để vừa theo dõi sức khỏe dependency vừa giới hạn concurrency.

Khi kết hợp, hãy xác định exception từ BulkheadFullException có được tính là lỗi của dependency hay không. Bulkhead đầy có thể là tình trạng quá tải ở caller, không nhất thiết phản ánh Inventory đang lỗi. Có thể cấu hình Circuit Breaker bỏ qua loại exception này nếu đó là chính sách mong muốn và phù hợp với cách lồng decorator.

## 10. Synchronization và lời gọi I/O

Một nguyên tắc quan trọng là không giữ lock của ứng dụng trong lúc gọi dịch vụ từ xa.

Ví dụ không nên làm:

~~~java
public synchronized InventoryResponse loadInventory(String sku) {
    return inventoryClient.getInventory(sku);
}
~~~

Từ khóa synchronized khóa toàn bộ phương thức trên cùng instance. Nếu Inventory mất 3 giây để phản hồi, các request khác gọi phương thức này phải chờ lock, kể cả khi chúng cần xử lý SKU khác. Điều này biến service thành một hàng đợi tuần tự và có thể tạo nghẽn ở caller.

Nếu cần bảo vệ một cập nhật nhỏ, hãy giữ critical section ngắn:

~~~java
private final Object lock = new Object();
private volatile String lastSuccessfulSku;

public InventoryResponse loadInventory(String sku) {
    InventoryResponse response = inventoryClient.getInventory(sku);

    synchronized (lock) {
        lastSuccessfulSku = sku;
    }

    return response;
}
~~~

Ví dụ trên chỉ minh họa phạm vi khóa nhỏ sau khi lời gọi từ xa hoàn tất. Trong ứng dụng thật, nếu chỉ lưu giá trị gần nhất, có thể dùng AtomicReference thay cho synchronized:

~~~java
private final AtomicReference<String> lastSuccessfulSku =
    new AtomicReference<>();

public void recordSuccess(String sku) {
    lastSuccessfulSku.set(sku);
}
~~~

Hãy chọn cơ chế đồng bộ hóa theo invariant cần bảo vệ. Nếu một thao tác cần cập nhật nhiều field như một giao dịch nguyên tử, một lock ngắn hoặc một cấu trúc dữ liệu chuyên dụng có thể phù hợp hơn. Không nên giữ lock qua HTTP I/O, database query hoặc thao tác chờ lâu.

## 11. Fallback và event listener cũng có thể chạy đồng thời

Fallback không mặc nhiên chạy tuần tự. Nếu nhiều request cùng gặp lỗi hoặc Circuit Breaker đang OPEN, nhiều fallback invocation có thể xảy ra gần như đồng thời.

Fallback nên:

- Không ghi vào field mutable dùng chung nếu không có đồng bộ hóa.
- Trả kết quả bất biến hoặc tạo response mới cho từng request.
- Tránh thực hiện I/O chậm nếu fallback nhằm giảm tải dependency.
- Không gọi lại chính dependency đang bị Circuit Breaker bảo vệ theo một đường không được kiểm soát.
- Ghi log đủ thông tin để phân biệt fallback do lỗi, timeout hay Circuit Breaker từ chối.

Event listener cũng cần được thiết kế ngắn gọn. Ví dụ listener ghi log state transition:

~~~java
inventoryBreaker.getEventPublisher()
    .onStateTransition(event ->
        log.warn(
            "Inventory CircuitBreaker state transition: {}",
            event.getStateTransition()
        )
    );
~~~

Không nên thực hiện truy vấn database, gọi HTTP hoặc gửi notification đồng bộ nặng ngay trong listener. Nếu cần xử lý công việc dài, hãy đưa event vào một hàng đợi có giới hạn hoặc cơ chế xử lý bất đồng bộ phù hợp. Khi chuyển event sang thread khác, cần cân nhắc thứ tự sự kiện, khả năng mất event và context propagation.

## 12. MDC, SecurityContext và ThreadLocal

MDC của SLF4J và SecurityContextHolder của Spring Security thường dựa trên ThreadLocal trong mô hình servlet mặc định. Khi lời gọi Circuit Breaker chạy trên cùng thread, context hiện tại thường có thể được đọc. Nhưng nếu ứng dụng dùng Thread Pool Bulkhead hoặc executor, công việc chuyển sang thread khác và ThreadLocal không tự động được sao chép.

Các trường hợp thường gặp:

- Semaphore Bulkhead giới hạn concurrency nhưng supplier vẫn chạy trên thread gọi; context ThreadLocal thường còn nguyên.
- Thread Pool Bulkhead chạy supplier trên thread pool riêng; MDC và SecurityContext cần context propagation.
- Fallback có thể chạy trong execution context khác tùy cách kết hợp các decorator và API; không nên giả định ThreadLocal luôn có mặt.
- Reactive pipeline có thể đổi thread giữa các operator; Reactor Context và cơ chế propagation cần được dùng phù hợp.

Với executor do ứng dụng quản lý, Spring Security có các wrapper như DelegatingSecurityContextExecutor. Với task executor của Spring, có thể dùng ContextPropagatingTaskDecorator khi đã cấu hình Micrometer Context Propagation. Nếu Resilience4j quản lý pool riêng, cần kiểm tra hook tích hợp mà phiên bản đang dùng hỗ trợ.

Không nên bật InheritableThreadLocal như giải pháp chung cho thread pool tái sử dụng. Context có thể tồn tại ngoài vòng đời request hoặc bị dùng nhầm giữa các tác vụ. Hãy luôn khôi phục hoặc xóa context trong finally.

## 13. Reactive và thread safety

Trong ứng dụng WebFlux, không nên giả định một request luôn ở cùng một thread. Reactor có thể chuyển xử lý giữa các scheduler và thread. ThreadLocal không phải nơi lưu context đáng tin cậy cho toàn bộ reactive pipeline.

Khi dùng reactive Circuit Breaker, hãy dùng API reactive tương ứng của Spring Cloud CircuitBreaker hoặc Resilience4j Reactor integration. Không gọi block(), Future.get() hoặc join() trên event-loop thread để chờ một lời gọi từ xa; điều đó có thể làm nghẽn event loop.

Reactor Context là cơ chế lưu metadata gắn với subscriber. Micrometer Context Propagation có thể hỗ trợ tích hợp với ThreadLocal khi được cấu hình, nhưng cần kiểm tra phiên bản Spring Boot, Reactor và Micrometer của ứng dụng. Đối với SecurityContext, dùng tích hợp reactive của Spring Security thay vì tự đọc ThreadLocal trong operator.

Một số nguyên tắc:

- Dùng Mono hoặc Flux xuyên suốt đường xử lý reactive.
- Không giữ mutable state dùng chung giữa các subscriber.
- Dùng Reactor Context cho dữ liệu theo subscriber.
- Dùng các operator thread-safe và tránh chia sẻ mutable collection không được bảo vệ.
- Giới hạn concurrency bằng Bulkhead hoặc giới hạn concurrency của reactive operator khi phù hợp.
- Tránh blocking I/O trên event-loop scheduler.

## 14. Kiểm thử hành vi đồng thời

Kiểm thử concurrency cần xác nhận cả kết quả lẫn giới hạn tài nguyên. Một phép thử đơn giản có thể dùng CountDownLatch để cho nhiều thread bắt đầu gọi cùng lúc, sau đó kiểm tra số lời gọi đồng thời đến supplier.

Ví dụ khung kiểm thử:

~~~java
CountDownLatch ready = new CountDownLatch(workerCount);
CountDownLatch start = new CountDownLatch(1);
AtomicInteger activeCalls = new AtomicInteger();
AtomicInteger maxObserved = new AtomicInteger();

Runnable task = () -> {
    ready.countDown();

    try {
        start.await();

        circuitBreaker.executeRunnable(() -> {
            int active = activeCalls.incrementAndGet();
            maxObserved.accumulateAndGet(active, Math::max);

            try {
                remoteCallWithControlledDelay();
            } finally {
                activeCalls.decrementAndGet();
            }
        });
    } catch (InterruptedException exception) {
        Thread.currentThread().interrupt();
    }
};
~~~

Sau khi tất cả worker sẵn sàng, test mở latch start để các lời gọi diễn ra đồng thời. Nếu chỉ dùng Circuit Breaker CLOSED mà không có Bulkhead, maxObserved có thể lớn hơn 1. Điều này minh họa Circuit Breaker không tuần tự hóa supplier.

Nếu bọc thêm Semaphore Bulkhead với maxConcurrentCalls bằng 5, phép thử có thể xác nhận số lời gọi đồng thời qua bulkhead không vượt quá giới hạn đó. Cần phân biệt các lời gọi bị từ chối với các lời gọi đã được thực thi.

Các kịch bản nên kiểm tra:

1. Nhiều thread gọi cùng một Circuit Breaker trong CLOSED.
2. Nhiều lỗi đồng thời làm Circuit Breaker chuyển OPEN.
3. Request mới bị từ chối sau khi mạch OPEN.
4. Lời gọi đã được cấp quyền trước khi OPEN vẫn có thể hoàn tất.
5. Số probe HALF_OPEN không vượt giới hạn.
6. Bulkhead giới hạn concurrency đúng cấu hình.
7. Fallback và event listener không làm chia sẻ mutable state sai cách.
8. MDC và SecurityContext được dọn sạch sau mỗi task.
9. Reactive pipeline không block event-loop.
10. Metrics và event không bị đăng ký trùng khi ứng dụng khởi động.

Khi kiểm thử, dùng fake dependency có độ trễ điều khiển được và kết quả lỗi xác định. Tránh phụ thuộc vào timing ngẫu nhiên vì test có thể chập chờn giữa các lần chạy.

## 15. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| Nhiều request vẫn cùng gọi dependency khi CLOSED | Circuit Breaker không phải concurrency limiter | Dùng Bulkhead nếu cần giới hạn số lời gọi đồng thời |
| Một số request vẫn hoàn tất sau khi state OPEN | Chúng đã được cấp quyền và bắt đầu trước khi mạch mở | Dùng timeout/cancellation để giới hạn in-flight calls |
| SKU hoặc dữ liệu request bị lẫn | Service singleton lưu request-specific state trong field | Truyền dữ liệu qua tham số hoặc context riêng từng lần gọi |
| Fallback ghi đè dữ liệu của request khác | Callback dùng mutable state chung | Tạo response riêng, dùng cấu trúc thread-safe |
| Log thiếu correlation ID sau khi dùng thread pool | MDC không được truyền sang thread mới | Cấu hình context propagation và cleanup |
| SecurityContext rỗng trong supplier | ThreadLocal không được chuyển sang executor | Dùng Spring Security context wrapper hoặc cơ chế tương thích |
| Event listener làm tăng latency | Listener thực hiện I/O blocking hoặc xử lý nặng | Giữ listener ngắn và offload công việc có giới hạn |
| Reactive request bị treo hoặc giảm throughput | Gọi block/get/join trên event loop | Dùng API reactive xuyên suốt |
| Synchronized service làm giảm throughput | Lock bao cả lời gọi I/O | Thu hẹp critical section hoặc dùng atomic/concurrent data structure |
| HALF_OPEN tạo burst lớn | Nhiều replica cùng thăm dò hoặc số probe quá cao | Giới hạn probe trên mỗi instance và tính tổng tải toàn hệ thống |

## 16. Nguyên tắc thiết kế

- Dùng chung Circuit Breaker instance do registry quản lý; không tạo một instance mới cho mỗi request.
- Xem thread safety của Resilience4j là bảo vệ trạng thái nội bộ, không phải bảo vệ mọi dữ liệu ứng dụng.
- Không giả định Circuit Breaker tuần tự hóa supplier hoặc giới hạn concurrency.
- Dùng Bulkhead để giới hạn số lời gọi đồng thời.
- Dùng timeout để giới hạn thời gian của lời gọi đang thực thi.
- Không giữ lock trong lúc gọi HTTP, database hoặc thao tác I/O chậm.
- Giữ Spring singleton service stateless hoặc chỉ chứa dữ liệu immutable/thread-safe.
- Thiết kế fallback và event listener để có thể được gọi đồng thời.
- Truyền MDC, SecurityContext và tracing context khi công việc chuyển thread.
- Dùng Reactor Context và API reactive trong WebFlux; tránh blocking trên event loop.
- Kiểm thử race condition, in-flight calls, HALF_OPEN và giới hạn Bulkhead bằng tải đồng thời có kiểm soát.

Resilience4j cung cấp các instance policy an toàn luồng để nhiều request có thể dùng chung. Circuit Breaker đồng bộ hóa việc quản lý state và thống kê, nhưng không khóa lời gọi từ xa và không giới hạn số request đang chạy. Mã ứng dụng cần giữ service singleton an toàn luồng, quản lý mutable state đúng cách và dùng Bulkhead cùng timeout khi cần kiểm soát tài nguyên. Khi hiểu rõ ranh giới này, ứng dụng Spring Cloud CircuitBreaker có thể xử lý concurrency ổn định mà không nhầm thread safety với giới hạn tải.

## Tài liệu tham khảo

- [Resilience4j CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker)
- [Resilience4j Bulkhead](https://resilience4j.readme.io/docs/bulkhead)
- [Resilience4j Retry](https://resilience4j.readme.io/docs/retry)
- [Spring Cloud CircuitBreaker reference](https://docs.spring.io/spring-cloud-circuitbreaker/reference/)
- [Spring Security concurrency support](https://docs.spring.io/spring-security/reference/servlet/integrations/concurrency.html)
- [Micrometer Context Propagation](https://docs.micrometer.io/context-propagation/reference/)
- [Project Reactor Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)

