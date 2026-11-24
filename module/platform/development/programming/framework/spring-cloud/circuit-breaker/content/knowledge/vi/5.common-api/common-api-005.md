# ReactiveCircuitBreakerFactory và ReactiveCircuitBreaker

Trong ứng dụng Spring Cloud sử dụng WebFlux và Reactor, các lời gọi đến dịch vụ phụ thuộc thường trả về Mono hoặc Flux. Để bảo vệ các lời gọi bất đồng bộ này, Spring Cloud CircuitBreaker cung cấp hai API reactive chính: ReactiveCircuitBreakerFactory và ReactiveCircuitBreaker.

ReactiveCircuitBreakerFactory tạo ra một Circuit Breaker theo tên cấu hình. ReactiveCircuitBreaker bao quanh một publisher Mono hoặc Flux, theo dõi kết quả thực thi và chuyển sang fallback khi publisher phát sinh lỗi hoặc Circuit Breaker từ chối lời gọi. Hai API này giúp lớp nghiệp vụ sử dụng cơ chế bảo vệ mà không cần phụ thuộc trực tiếp vào các lớp triển khai riêng của Resilience4j.

Bài học tập trung vào cách tạo, sử dụng và cấu hình hai API reactive này trong Spring Cloud CircuitBreaker với Resilience4j, cách viết fallback đúng kiểu dữ liệu, cách kết hợp timeout và cách tránh những lỗi thường gặp trong luồng Reactor.

## 1. Vai trò của hai API

Hai thành phần có trách nhiệm khác nhau:

- **ReactiveCircuitBreakerFactory** là factory được Spring quản lý và inject vào ứng dụng. Nó tạo ReactiveCircuitBreaker theo một ID, ví dụ inventory hoặc payment.
- **ReactiveCircuitBreaker** là đối tượng bảo vệ một lời gọi reactive cụ thể. Nó nhận Mono hoặc Flux, thực thi publisher khi có subscription, ghi nhận kết quả và áp dụng fallback khi có lỗi.

Luồng xử lý khái quát:

~~~mermaid
flowchart TD
    A[Service nhận yêu cầu] --> B[ReactiveCircuitBreakerFactory]
    B --> C[Tạo hoặc lấy breaker theo ID]
    C --> D[ReactiveCircuitBreaker.run]
    D --> E[Mono hoặc Flux gọi dependency]
    E --> F{Kết quả publisher}
    F -- Thành công --> G[Trả dữ liệu cho caller]
    F -- Lỗi hoặc bị từ chối --> H[Chạy fallback publisher]
    H --> I[Trả kết quả suy giảm hoặc lỗi có kiểm soát]
~~~

Factory thường được inject một lần vào service, sau đó tạo breaker theo ID trong constructor hoặc lúc khởi tạo thành phần. Việc dùng ID ổn định giúp breaker gắn với cấu hình tương ứng và số liệu theo dõi có thể được phân biệt theo dependency.

## 2. ReactiveCircuitBreakerFactory

Trong Spring Cloud CircuitBreaker, ReactiveCircuitBreakerFactory là điểm truy cập để tạo reactive breaker. Cách dùng cơ bản:

~~~java
ReactiveCircuitBreaker inventoryBreaker =
        circuitBreakerFactory.create("inventory");
~~~

Chuỗi inventory là ID của Circuit Breaker. Khi sử dụng implementation Resilience4j, ID này liên kết với cấu hình instance tương ứng trong application.yml, ví dụ:

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
        slowCallRateThreshold: 50
        waitDurationInOpenState: 10s
        permittedNumberOfCallsInHalfOpenState: 3
~~~

Trong cấu hình trên, inventory là tên instance. Nếu code tạo breaker bằng ID khác, chẳng hạn inventory-api, cấu hình inventory sẽ không tự động áp dụng cho ID mới đó. Hãy giữ tên trong code và tên instance trong cấu hình thống nhất.

Factory che giấu chi tiết implementation. Service chỉ cần biết interface ReactiveCircuitBreakerFactory và ReactiveCircuitBreaker. Nhờ đó, logic gọi dependency ít bị gắn chặt với Resilience4j, thuận lợi hơn khi thay đổi implementation hoặc cấu hình theo môi trường.

Ví dụ inject factory vào service:

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;

@Service
public class InventoryService {

    private final ReactiveCircuitBreaker inventoryBreaker;

    public InventoryService(
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.inventoryBreaker = circuitBreakerFactory.create("inventory");
    }
}
~~~

Các tham số generic của factory có thể khác nhau theo phiên bản và implementation. Dùng interface do Spring Cloud cung cấp để giữ code ở tầng ứng dụng độc lập với API cấu hình nội bộ của Resilience4j.

## 3. ReactiveCircuitBreaker và phương thức run

ReactiveCircuitBreaker cung cấp phương thức run cho hai kiểu publisher phổ biến:

- Mono<T> đại diện cho một kết quả bất đồng bộ có thể có hoặc không có giá trị.
- Flux<T> đại diện cho một chuỗi gồm không, một hoặc nhiều phần tử bất đồng bộ.

Với Mono, cách gọi có dạng:

~~~java
<T> Mono<T> run(
        Mono<T> toRun,
        Function<Throwable, Mono<T>> fallback);
~~~

Với Flux, cách gọi có dạng:

~~~java
<T> Flux<T> run(
        Flux<T> toRun,
        Function<Throwable, Flux<T>> fallback);
~~~

Tham số toRun là publisher thực hiện lời gọi cần bảo vệ. Tham số fallback là hàm nhận nguyên nhân lỗi và trả về publisher thay thế có cùng kiểu phần tử.

Ví dụ với Mono:

~~~java
Mono<Inventory> result = inventoryBreaker.run(
        inventoryClient.findInventory(sku),
        error -> Mono.just(Inventory.unavailable(sku))
);
~~~

Ví dụ với Flux:

~~~java
Flux<Inventory> result = inventoryBreaker.run(
        inventoryClient.findAllInventory(),
        error -> inventoryCache.findAllAvailable()
);
~~~

Fallback của Mono phải trả Mono cùng kiểu dữ liệu. Fallback của Flux phải trả Flux cùng kiểu phần tử. Không thể trả Mono từ fallback của một lời gọi Flux hoặc ngược lại.

Các publisher trong Reactor là lazy: việc tạo Mono hoặc Flux chưa có nghĩa request đã được gửi đi. Publisher bắt đầu thực thi khi có subscription. ReactiveCircuitBreaker bọc publisher để theo dõi quá trình thực thi đó. Vì vậy, không nên gọi subscribe() bên trong service chỉ để kích hoạt lời gọi; hãy trả publisher cho tầng gọi phía trên để toàn bộ luồng được compose và subscribe tại đúng điểm.

## 4. Tích hợp với WebClient

Một trường hợp thường gặp là service dùng WebClient gọi dịch vụ tồn kho. Starter reactive của Spring Cloud CircuitBreaker với Resilience4j có thể được thêm vào ứng dụng:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-circuitbreaker-reactor-resilience4j</artifactId>
</dependency>
~~~

Quản lý phiên bản Spring Cloud bằng BOM tương thích với phiên bản Spring Boot đang dùng. Không nên tự chọn một phiên bản starter riêng lẻ mà bỏ qua ma trận tương thích của dự án.

Ví dụ service bảo vệ lời gọi WebClient:

~~~java
import java.time.Duration;

import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

import reactor.core.publisher.Mono;

@Service
public class InventoryClient {

    private final WebClient webClient;
    private final ReactiveCircuitBreaker inventoryBreaker;

    public InventoryClient(
            WebClient.Builder webClientBuilder,
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory) {
        this.webClient = webClientBuilder
                .baseUrl("http://inventory-service")
                .build();
        this.inventoryBreaker = circuitBreakerFactory.create("inventory");
    }

    public Mono<Inventory> findInventory(String sku) {
        Mono<Inventory> remoteCall = webClient.get()
                .uri("/inventory/{sku}", sku)
                .retrieve()
                .bodyToMono(Inventory.class)
                .timeout(Duration.ofSeconds(2));

        return inventoryBreaker.run(
                remoteCall,
                error -> fallback(sku, error)
        );
    }

    private Mono<Inventory> fallback(String sku, Throwable error) {
        return Mono.just(Inventory.unavailable(sku));
    }
}
~~~

Inventory là kiểu dữ liệu của ứng dụng; phương thức unavailable trong ví dụ đại diện cho cách tạo kết quả suy giảm theo mô hình nghiệp vụ. Cần thay bằng model và chính sách fallback thực tế của dự án.

Trong ví dụ, timeout được đặt trên publisher remoteCall trước khi truyền vào run. Khi lời gọi vượt quá hai giây, Reactor phát sinh lỗi timeout và Circuit Breaker có thể ghi nhận kết quả đó theo chính sách phân loại lỗi. Nếu đặt timeout ở một tầng bên ngoài không được Circuit Breaker quan sát, phép đo của breaker có thể không phản ánh đầy đủ thời gian chờ mà caller thực sự trải qua.

WebClient phát sinh lỗi cho response HTTP không thành công khi dùng retrieve() với cấu hình mặc định. Cần quyết định mã lỗi nào là lỗi hạ tầng và mã nào là kết quả nghiệp vụ bình thường. Ví dụ, 404 có thể có nghĩa sản phẩm không tồn tại, không nhất thiết là dịch vụ tồn kho bị hỏng. Có thể xử lý và phân loại lỗi HTTP trước khi để lỗi đi vào Circuit Breaker.

## 5. Viết fallback đúng cách

Fallback là publisher thay thế khi lời gọi chính phát sinh lỗi hoặc bị từ chối bởi Circuit Breaker đang OPEN. Hàm fallback nhận Throwable, vì vậy có thể kiểm tra nguyên nhân để lựa chọn cách phản hồi:

~~~java
private Mono<Inventory> fallback(String sku, Throwable error) {
    if (error instanceof CallNotPermittedException) {
        return cachedInventory(sku);
    }

    if (error instanceof TimeoutException) {
        return cachedInventory(sku);
    }

    return Mono.error(error);
}
~~~

Ví dụ trên minh họa cách phân nhánh theo loại lỗi; cần import đúng lớp exception và định nghĩa cachedInventory theo ứng dụng. Nếu không có dữ liệu cache hoặc không thể tạo kết quả suy giảm an toàn, fallback có thể trả lỗi tiếp để caller xử lý. Không nên biến mọi lỗi thành một response thành công giả.

Một fallback tốt cần đáp ứng các nguyên tắc:

- **Cùng kiểu dữ liệu**: Mono<T> phải được thay bằng Mono<T>; Flux<T> phải được thay bằng Flux<T>.
- **Không chặn event loop**: tránh block(), gọi I/O đồng bộ hoặc chờ Future bằng cách chặn thread trong fallback.
- **Có ý nghĩa nghiệp vụ**: có thể trả dữ liệu cache, trạng thái tạm thời hoặc một kết quả suy giảm đã được định nghĩa.
- **Không che giấu sự cố**: ghi log và metric về nguyên nhân fallback, phân biệt timeout, lỗi từ xa và lời gọi bị Circuit Breaker từ chối.
- **Không tạo thêm dependency mong manh**: fallback gọi một dịch vụ từ xa khác có thể làm xuất hiện một điểm lỗi thứ hai.

Fallback không phải là retry. Retry gọi lại thao tác chính theo chính sách thử lại; fallback tạo một luồng thay thế khi thao tác chính không thể cung cấp kết quả. Hai cơ chế có thể được kết hợp nhưng cần giới hạn số lần thử và thời gian tổng thể.

## 6. Bảo vệ Flux và xử lý luồng nhiều phần tử

Với Flux, một lỗi có thể xảy ra sau khi một số phần tử đã được phát ra. Khi publisher phát tín hiệu onError, luồng ban đầu kết thúc. ReactiveCircuitBreaker có thể chuyển sang publisher fallback được cung cấp. Fallback cần được thiết kế phù hợp với ngữ nghĩa dữ liệu của ứng dụng.

Ví dụ, một API trả về danh sách tồn kho:

~~~java
public Flux<Inventory> findAllInventory() {
    Flux<Inventory> remoteStream = webClient.get()
            .uri("/inventory")
            .retrieve()
            .bodyToFlux(Inventory.class)
            .timeout(Duration.ofSeconds(3));

    return inventoryBreaker.run(
            remoteStream,
            error -> inventoryCache.findAllAvailable()
    );
}
~~~

Nếu remoteStream lỗi, fallback trả về Flux từ cache. Cần xác định rõ dữ liệu cache có thể cũ đến mức nào và caller có cần biết kết quả đến từ cache hay không. Nếu API cần phân biệt dữ liệu trực tiếp và dữ liệu suy giảm, có thể biểu diễn nguồn dữ liệu trong kiểu response hoặc metadata nghiệp vụ.

Không nên mặc định fallback là Flux.empty() cho mọi lỗi. Một luồng rỗng có thể bị caller hiểu là dependency hoạt động bình thường nhưng không có dữ liệu. Nếu lỗi thực sự quan trọng, hãy phát sinh lỗi hoặc trả trạng thái suy giảm có thể nhận biết.

## 7. Kết hợp timeout và Circuit Breaker

ReactiveCircuitBreaker theo dõi kết quả của publisher; timeout xác định giới hạn thời gian chờ của publisher đó. Hai cơ chế có thể phối hợp để tránh một lời gọi chậm giữ tài nguyên quá lâu và để Circuit Breaker có dữ liệu nhận diện dependency đang suy giảm.

Ví dụ:

~~~java
Mono<Product> remoteCall = webClient.get()
        .uri("/products/{id}", productId)
        .retrieve()
        .bodyToMono(Product.class)
        .timeout(Duration.ofSeconds(2));

return productBreaker.run(
        remoteCall,
        error -> productCache.find(productId)
);
~~~

Khi timeout được đặt trong publisher truyền vào run, timeout trở thành một lỗi mà Circuit Breaker có thể ghi nhận. Khi tỷ lệ lỗi hoặc tỷ lệ lời gọi chậm đạt ngưỡng, Circuit Breaker có thể chuyển OPEN và từ chối các lời gọi mới trong thời gian chờ.

Cần phân biệt timeout của từng lần gọi với deadline của toàn bộ request. Nếu request có nhiều dependency hoặc có retry, tổng thời gian xử lý có thể dài hơn timeout của một publisher. Hãy tính cả thời gian chờ, retry, fallback và thời gian xử lý ở các tầng phía trên để không vượt SLA.

## 8. Cấu hình theo ID và quản lý nhiều dependency

Mỗi dependency có đặc điểm độ trễ, lưu lượng và độ tin cậy khác nhau. Nên đặt ID riêng cho các Circuit Breaker có chính sách vận hành khác nhau. Ví dụ:

~~~yaml
resilience4j:
  circuitbreaker:
    instances:
      inventory:
        slidingWindowType: COUNT_BASED
        slidingWindowSize: 20
        minimumNumberOfCalls: 10
        failureRateThreshold: 50
        waitDurationInOpenState: 10s
      payment:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 10
        minimumNumberOfCalls: 20
        failureRateThreshold: 40
        waitDurationInOpenState: 15s
~~~

Trong code, tạo breaker bằng đúng ID tương ứng:

~~~java
this.inventoryBreaker = circuitBreakerFactory.create("inventory");
this.paymentBreaker = circuitBreakerFactory.create("payment");
~~~

Không nên dùng chung một ID cho các dependency có đặc tính lỗi khác nhau nếu cần theo dõi và tinh chỉnh riêng. Ngược lại, cũng không nên tạo ID mới cho từng request hoặc từng giá trị có cardinality cao. Số lượng instance tăng sẽ làm tăng trạng thái và tài nguyên thống kê cần duy trì.

Nếu ứng dụng dùng nhiều profile, hãy đặt cấu hình phù hợp cho từng môi trường. Cấu hình phát triển có thể đơn giản để dễ kiểm thử; cấu hình production cần dựa trên lưu lượng, SLA và số liệu thực tế.

## 9. Theo dõi và quan sát hoạt động reactive breaker

Resilience4j có thể tích hợp với Micrometer và Spring Boot Actuator để xuất metric. Khi bật các endpoint và registry tương ứng, hệ thống giám sát có thể theo dõi tình trạng của từng breaker.

Các chỉ số nên theo dõi:

- Trạng thái hiện tại của từng breaker: CLOSED, OPEN hoặc HALF_OPEN.
- Số lời gọi thành công, thất bại, chậm và bị từ chối.
- Số lần fallback được sử dụng và loại nguyên nhân gây fallback.
- Độ trễ của publisher chính và thời gian phản hồi cuối cùng sau fallback.
- Tỷ lệ timeout, lỗi HTTP và lỗi kết nối theo dependency.
- Số lượng breaker instance và sự thay đổi theo thời gian.

Metric cần có nhãn vừa đủ để phân biệt dependency. Tránh đưa ID request, user ID hoặc giá trị động có cardinality cao vào nhãn metric. Những thông tin cần truy vết một request cụ thể phù hợp hơn với trace và log có tương quan.

Khi breaker thường xuyên OPEN, kiểm tra độ trễ và lỗi gốc của dependency, timeout, ngưỡng thống kê và cách phân loại exception. Khi fallback tăng cao nhưng tỷ lệ request thành công vẫn tốt, cần thể hiện riêng tỷ lệ fallback để dashboard không che khuất sự suy giảm chất lượng.

## 10. Những lỗi thường gặp khi sử dụng API reactive

- **Dùng CircuitBreakerFactory đồng bộ cho publisher reactive**: chọn ReactiveCircuitBreakerFactory khi lời gọi cần bảo vệ trả Mono hoặc Flux để giữ đúng mô hình xử lý.
- **Không khớp ID cấu hình**: ID truyền vào create phải khớp với tên instance trong cấu hình Resilience4j.
- **Fallback sai kiểu publisher**: fallback Mono và Flux không thể hoán đổi cho nhau.
- **Gọi block() trong luồng WebFlux**: thao tác chặn có thể chiếm event loop và làm giảm khả năng xử lý đồng thời.
- **Tự subscribe() trong service**: việc này tách lời gọi khỏi chuỗi reactive do tầng gọi quản lý và có thể làm mất khả năng compose, xử lý lỗi hoặc quản lý vòng đời.
- **Fallback luôn trả dữ liệu giả**: caller có thể hiểu nhầm dữ liệu suy giảm là dữ liệu mới nhất.
- **Không phân loại lỗi nghiệp vụ**: lỗi như 404 có thể bị tính như lỗi dependency nếu không được xử lý phù hợp.
- **Đặt timeout sai vị trí**: Circuit Breaker có thể không ghi nhận lỗi timeout nếu timeout nằm ngoài publisher được bảo vệ.
- **Fallback gọi dịch vụ từ xa không được bảo vệ**: sự cố có thể chuyển sang dependency thứ hai và tiếp tục lan rộng.

## 11. Quy trình triển khai

Khi tích hợp ReactiveCircuitBreakerFactory và ReactiveCircuitBreaker vào một service WebFlux, có thể thực hiện theo trình tự:

1. Thêm starter reactive Resilience4j và dùng BOM tương thích với Spring Boot.
2. Inject ReactiveCircuitBreakerFactory vào service hoặc lớp client phụ thuộc.
3. Tạo breaker bằng ID ổn định, đại diện cho dependency cần bảo vệ.
4. Khai báo cấu hình Resilience4j với cùng ID trong application.yml.
5. Tạo Mono hoặc Flux cho lời gọi WebClient và đặt timeout phù hợp.
6. Truyền publisher cùng fallback đúng kiểu vào ReactiveCircuitBreaker.run.
7. Thiết kế fallback có ý nghĩa nghiệp vụ, không block và có thể quan sát.
8. Theo dõi trạng thái, số liệu lỗi, timeout và tỷ lệ fallback trong môi trường chạy thực tế.

ReactiveCircuitBreakerFactory cung cấp cách tạo breaker theo ID; ReactiveCircuitBreaker.run áp dụng cơ chế bảo vệ cho Mono và Flux. Khi sử dụng đúng kiểu publisher, cấu hình khớp ID, timeout phù hợp và fallback được thiết kế cẩn thận, ứng dụng Spring Cloud có thể bảo vệ các lời gọi reactive đến dependency mà vẫn giữ được tính bất đồng bộ của Reactor.
