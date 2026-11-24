# Bao WebClient bằng ReactiveCircuitBreakerFactory

Trong ứng dụng Spring WebFlux, `WebClient` thực hiện lời gọi HTTP theo mô hình reactive và trả về publisher như `Mono<T>` hoặc `Flux<T>`. Để bảo vệ lời gọi đó bằng Circuit Breaker, Spring Cloud CircuitBreaker cung cấp `ReactiveCircuitBreakerFactory`. Factory tạo một Circuit Breaker theo tên; đối tượng được tạo có thể bọc publisher của `WebClient` và áp dụng fallback khi lời gọi phát sinh lỗi hoặc bị từ chối.

Trong module **SPRING_CLOUD_CIRCUIT_BREAKER**, cách tích hợp này giúp ngăn lỗi dây chuyền khi dịch vụ phụ thuộc chậm hoặc không khả dụng. Ta cần giữ nguyên chuỗi reactive từ lúc tạo request đến lúc trả kết quả, để Circuit Breaker quan sát được tín hiệu thành công, lỗi và thời gian thực hiện mà không chặn luồng bằng `block()`.

## 1. Vai trò của ReactiveCircuitBreakerFactory

`ReactiveCircuitBreakerFactory` là điểm tạo Circuit Breaker reactive trong Spring Cloud abstraction. Ứng dụng thường inject factory vào service hoặc component gọi dịch vụ phụ thuộc, rồi gọi `create(name)` để lấy Circuit Breaker tương ứng.

Các thành phần chính:

| Thành phần | Vai trò |
| --- | --- |
| `WebClient` | Tạo request HTTP và trả về publisher reactive |
| `ReactiveCircuitBreakerFactory` | Tạo Circuit Breaker theo định danh |
| `ReactiveCircuitBreaker` | Bọc publisher chính, theo dõi kết quả và chuyển lỗi cho fallback |
| `Mono<T>` | Kiểu publisher được API `ReactiveCircuitBreaker.run` của Spring Cloud sử dụng cho một kết quả hoặc một luồng hoàn tất |
| `Flux<T>` | Publisher nhiều phần tử do WebClient có thể trả về; với luồng streaming, cần chọn cách tích hợp phù hợp thay vì giả định mọi overload của Spring Cloud abstraction nhận trực tiếp Flux |
| Fallback | Tạo publisher dự phòng khi publisher chính thất bại hoặc Circuit Breaker từ chối lời gọi |

Luồng tổng quát:

~~~mermaid
flowchart TD
    A[Service nhận yêu cầu] --> B[Tạo ReactiveCircuitBreaker theo tên]
    B --> C[Tạo publisher từ WebClient]
    C --> D[ReactiveCircuitBreaker.run]
    D --> E{Publisher chính}
    E -->|Hoàn tất thành công| F[Trả dữ liệu từ dịch vụ phụ thuộc]
    E -->|Phát onError| G[Fallback nhận Throwable]
    E -->|Mạch OPEN| G
    G --> H[Publisher dự phòng]
    F --> I[Trả kết quả reactive cho bên gọi]
    H --> I
~~~

Điểm quan trọng là publisher của `WebClient` phải được truyền vào `ReactiveCircuitBreaker.run`. Khi publisher phát tín hiệu `onError`, Circuit Breaker có thể ghi nhận lời gọi thất bại và gọi fallback nếu đã được cung cấp.

## 2. Khai báo dependency và cấu hình

Ứng dụng cần có Spring Cloud CircuitBreaker starter tương ứng với Resilience4j và dependency WebFlux để dùng `WebClient`. Tên artifact cụ thể cần chọn theo release train Spring Cloud và phiên bản Spring Boot mà dự án đang sử dụng; không nên trộn các phiên bản không tương thích.

Ví dụ cấu hình Circuit Breaker có tên `inventory` trong `application.yml`:

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
        permittedNumberOfCallsInHalfOpenState: 3
~~~

Trong ví dụ, Circuit Breaker theo dõi 20 lời gọi gần nhất và cần tối thiểu 10 kết quả trước khi đánh giá tỷ lệ. Nếu tỷ lệ lỗi đạt 50% hoặc tỷ lệ lời gọi chậm đạt 60%, mạch có thể chuyển sang OPEN. Sau thời gian chờ 10 giây, mạch cho phép tối đa 3 lời gọi thử nghiệm trong HALF_OPEN.

Đây là các giá trị minh họa. Cần điều chỉnh theo lưu lượng, độ trễ bình thường, timeout của HTTP client và mục tiêu phục vụ của dịch vụ phụ thuộc. Tên `inventory` trong cấu hình phải trùng với tên truyền vào `reactiveCircuitBreakerFactory.create("inventory")`.

## 3. Tạo WebClient và inject factory

Có thể khai báo `WebClient` dùng chung bằng bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration
public class HttpClientConfiguration {
    @Bean
    WebClient inventoryWebClient(WebClient.Builder builder) {
        return builder
                .baseUrl("http://inventory-service")
                .build();
    }
}
~~~

Trong service, inject `ReactiveCircuitBreakerFactory` và `WebClient`:

~~~java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;

@Service
public class InventoryGateway {
    private final ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory;
    private final WebClient inventoryWebClient;

    public InventoryGateway(
            ReactiveCircuitBreakerFactory<?, ?> circuitBreakerFactory,
            WebClient inventoryWebClient) {
        this.circuitBreakerFactory = circuitBreakerFactory;
        this.inventoryWebClient = inventoryWebClient;
    }
}
~~~

Spring inject factory được cấu hình bởi implementation đang dùng, ví dụ Resilience4j. Wildcard trong kiểu generic giúp service không phụ thuộc trực tiếp vào kiểu cấu hình nội bộ của implementation.

## 4. Bọc lời gọi WebClient bằng ReactiveCircuitBreaker

Phương thức `getInventory` dưới đây gọi dịch vụ Kho và trả về `Mono<Inventory>`:

~~~java
import reactor.core.publisher.Mono;

public Mono<Inventory> getInventory(String sku) {
    ReactiveCircuitBreaker circuitBreaker =
            circuitBreakerFactory.create("inventory");

    Mono<Inventory> primary = inventoryWebClient.get()
            .uri("/items/{sku}", sku)
            .retrieve()
            .bodyToMono(Inventory.class);

    return circuitBreaker.run(
            primary,
            failure -> Mono.just(Inventory.unavailable(sku))
    );
}
~~~

Đoạn mã thực hiện ba bước:

1. Factory tạo Circuit Breaker có tên `inventory`.
2. `WebClient` tạo publisher chính. Request chưa nhất thiết được gửi ngay tại dòng khai báo; publisher của WebClient là lazy và việc thực thi diễn ra khi có subscription.
3. `circuitBreaker.run` bọc publisher chính và nhận hàm fallback. Fallback nhận `Throwable` và trả về một `Mono<Inventory>` có kiểu tương thích với publisher chính.

Nếu dịch vụ Kho trả kết quả hợp lệ, `Mono` phát ra dữ liệu và hoàn tất. Nếu lời gọi phát sinh exception, Circuit Breaker có thể ghi nhận lỗi rồi chuyển nguyên nhân đến fallback. Nếu mạch đang OPEN, lời gọi bị từ chối trước khi request được gửi đến dịch vụ phụ thuộc; fallback có thể xử lý lỗi từ chối đó.

Ví dụ giả định ứng dụng có lớp `Inventory` với phương thức `unavailable(sku)` để biểu diễn trạng thái không thể xác minh tồn kho. Không nên dùng số lượng bằng 0 làm fallback nếu 0 mang nghĩa đã xác nhận hết hàng.

## 5. Chuyển HTTP status thành exception

Với `retrieve()`, WebClient mặc định phát `WebClientResponseException` cho response 4xx và 5xx. Có thể dùng hành vi mặc định này để Circuit Breaker quan sát lỗi HTTP. Khi muốn phân loại status theo nghiệp vụ, dùng `onStatus`:

~~~java
private Mono<Inventory> requestInventory(String sku) {
    return inventoryWebClient.get()
            .uri("/items/{sku}", sku)
            .retrieve()
            .onStatus(
                    status -> status.value() == 404,
                    response -> Mono.error(
                            new InventoryNotFoundException(sku))
            )
            .onStatus(
                    status -> status.is5xxServerError(),
                    response -> response.createException()
            )
            .bodyToMono(Inventory.class);
}

public Mono<Inventory> getInventory(String sku) {
    ReactiveCircuitBreaker circuitBreaker =
            circuitBreakerFactory.create("inventory");

    return circuitBreaker.run(
            requestInventory(sku),
            failure -> fallbackInventory(sku, failure)
    );
}
~~~

Trong ví dụ, 404 được chuyển thành exception nghiệp vụ riêng; nhóm 5xx dùng exception do WebClient tạo. Nếu 404 là kết quả nghiệp vụ bình thường, có thể cấu hình Resilience4j bỏ qua `InventoryNotFoundException` khi tính failure rate, đồng thời vẫn cho tầng gọi xử lý exception đó theo đúng nghĩa.

Ví dụ fallback phân biệt lỗi:

~~~java
private Mono<Inventory> fallbackInventory(String sku, Throwable failure) {
    if (failure instanceof InventoryNotFoundException) {
        return Mono.error(failure);
    }

    return inventoryCache.findRecent(sku)
            .map(value -> value.withStale(true))
            .defaultIfEmpty(Inventory.unavailable(sku));
}
~~~

Fallback trả dữ liệu cache nếu có và đánh dấu dữ liệu cũ. Nếu không có cache, nó trả trạng thái unavailable. Với lỗi nghiệp vụ không tìm thấy sản phẩm, fallback chuyển tiếp lỗi để API có thể trả phản hồi phù hợp.

Không nên dùng `onErrorReturn` hoặc `onErrorResume` để biến lỗi thành dữ liệu thành công trước khi đưa publisher vào Circuit Breaker nếu mục tiêu là để Circuit Breaker ghi nhận lỗi gốc. Hãy để tín hiệu lỗi truyền đến `run`, rồi xử lý qua fallback của Circuit Breaker hoặc ở tầng ngoài sau đó.

## 6. Fallback phải trả publisher tương thích

Với API `ReactiveCircuitBreaker` của Spring Cloud, lời gọi chính và fallback thường dùng `Mono<T>`; fallback không trả trực tiếp một đối tượng `Inventory` mà trả một `Mono<Inventory>`. Khi cần bảo vệ `Flux<T>` streaming, dùng cách tích hợp Resilience4j Reactor operator được trình bày ở phần sau, trong đó publisher fallback có thể được nối bằng các operator Reactor.

Ví dụ fallback bằng cache:

~~~java
private Mono<Inventory> fallbackFromCache(String sku, Throwable failure) {
    return inventoryCache.findRecent(sku)
            .switchIfEmpty(Mono.just(Inventory.unavailable(sku)));
}
~~~

Có thể truyền method reference nếu chữ ký phù hợp:

~~~java
return circuitBreaker.run(
        requestInventory(sku),
        this::fallbackFromCache
);
~~~

Trong trường hợp fallback cần thêm ngữ cảnh như `sku`, lambda giúp truyền biến đó cùng với `Throwable`:

~~~java
return circuitBreaker.run(
        requestInventory(sku),
        failure -> fallbackFromCache(sku, failure)
);
~~~

Không gọi `block()` để lấy dữ liệu cache bên trong fallback. Việc đó chặn luồng và làm mất lợi ích của reactive. Hãy trả về publisher của cache để Reactor kết hợp các thao tác bất đồng bộ.

Nếu chính fallback phát sinh lỗi, publisher kết quả sẽ phát `onError` và lỗi đó được chuyển đến tầng gọi phía trên. Cần quan sát cả lỗi của lời gọi chính lẫn lỗi khi tạo kết quả dự phòng.

## 7. Thêm timeout cho publisher

Circuit Breaker có thể đánh giá lời gọi chậm thông qua `slowCallDurationThreshold`, nhưng ngưỡng này không thay thế timeout. Nếu lời gọi không bao giờ hoàn tất, ứng dụng cần giới hạn thời gian chờ để publisher phát lỗi timeout và giải phóng các tài nguyên liên quan.

Có thể đặt timeout trên publisher:

~~~java
import java.time.Duration;

private Mono<Inventory> requestInventory(String sku) {
    return inventoryWebClient.get()
            .uri("/items/{sku}", sku)
            .retrieve()
            .bodyToMono(Inventory.class)
            .timeout(Duration.ofSeconds(2));
}
~~~

Khi timeout xảy ra, publisher phát lỗi `TimeoutException`; nếu timeout nằm bên trong publisher được truyền cho Circuit Breaker, Circuit Breaker có thể quan sát lỗi này và áp dụng chính sách ghi nhận. Có thể cấu hình TimeLimiter riêng của Resilience4j hoặc timeout của HTTP client tùy yêu cầu. Tránh cấu hình nhiều timeout chồng lấn mà không xác định rõ giới hạn nào có hiệu lực trước.

Nếu cần dùng TimeLimiter, hãy kiểm tra cấu hình reactive của phiên bản Spring Cloud CircuitBreaker và Resilience4j đang dùng. Cách cấu hình timeout có thể khác giữa các phiên bản và loại client.

## 8. Hiểu lazy execution, subscription và cancellation

Publisher của WebClient là lazy: khai báo biến `Mono` không đồng nghĩa request đã được gửi. Request được kích hoạt khi có subscriber. Circuit Breaker bọc publisher và áp dụng logic bảo vệ trong quá trình subscription.

Điều này dẫn đến một số hệ quả:

- Nếu controller hoặc tầng gọi không subscribe publisher và cũng không trả nó cho một runtime reactive quản lý, request sẽ không chạy.
- Không nên gọi `subscribe()` thủ công trong service chỉ để “kích hoạt” request; hãy trả publisher cho tầng gọi để WebFlux quản lý subscription và lỗi.
- Khi client hủy subscription, tín hiệu cancellation có thể được truyền xuống publisher nguồn. Không nên xem cancellation do người gọi rời đi là lỗi HTTP thông thường.
- Nếu dùng `Mono.defer`, phần tạo publisher được thực hiện cho từng subscription. Cách này hữu ích khi cần đọc dữ liệu hoặc tạo thao tác tại thời điểm thực thi.

Ví dụ dùng `defer`:

~~~java
Mono<Inventory> primary = Mono.defer(() ->
        inventoryWebClient.get()
                .uri("/items/{sku}", sku)
                .retrieve()
                .bodyToMono(Inventory.class)
);

return circuitBreaker.run(
        primary,
        failure -> fallbackInventory(sku, failure)
);
~~~

Không cần bọc mọi lời gọi WebClient bằng `Mono.defer`; WebClient đã tạo publisher lazy. Chỉ dùng khi muốn trì hoãn cả bước xây dựng publisher hoặc khi có dữ liệu cần lấy lại ở mỗi subscription.

## 9. Kết hợp với Flux và luồng dữ liệu nhiều phần tử

Với endpoint trả nhiều phần tử, WebClient có thể trả về `Flux<Item>`. API `ReactiveCircuitBreaker` trong Spring Cloud abstraction thường cung cấp overload `run(Mono<T>, Function<Throwable, Mono<T>>)`; vì vậy không nên mặc định rằng có thể truyền trực tiếp `Flux<T>` vào factory-created circuit breaker.

Nếu luồng hữu hạn và số phần tử được giới hạn, có thể thu thập thành `Mono<List<Item>>`, bảo vệ Mono đó bằng factory rồi chuyển danh sách trở lại Flux:

~~~java
public Flux<Item> getItems() {
    ReactiveCircuitBreaker circuitBreaker =
            circuitBreakerFactory.create("catalog");

    Mono<List<Item>> primary = catalogWebClient.get()
            .uri("/items")
            .retrieve()
            .bodyToFlux(Item.class)
            .collectList();

    return circuitBreaker.run(
            primary,
            failure -> fallbackItems(failure).collectList()
    ).flatMapMany(Flux::fromIterable);
}
~~~

Phương án này đệm toàn bộ danh sách trong bộ nhớ trước khi trả phần tử đầu tiên. Chỉ dùng khi kết quả có giới hạn và việc thu thập toàn bộ dữ liệu là phù hợp. Fallback phải trả `Mono<List<Item>>` để khớp kiểu với publisher chính. Một danh sách rỗng có thể khiến bên gọi hiểu rằng danh mục thực sự không có sản phẩm, trong khi nguyên nhân thật là dịch vụ không khả dụng; hãy chọn kiểu kết quả có trạng thái rõ ràng hoặc phát lỗi phù hợp.

Với luồng streaming dài hoặc không giới hạn, không nên thu thập toàn bộ dữ liệu vào một danh sách. Nếu ứng dụng dùng Resilience4j Reactor module, có thể áp dụng `CircuitBreakerOperator` trực tiếp lên Flux rồi xử lý lỗi sau operator:

~~~java
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.reactor.circuitbreaker.operator.CircuitBreakerOperator;
import reactor.core.publisher.Flux;

public Flux<Item> streamItems() {
    CircuitBreaker circuitBreaker =
            circuitBreakerRegistry.circuitBreaker("catalog");

    return catalogWebClient.get()
            .uri("/items/stream")
            .retrieve()
            .bodyToFlux(Item.class)
            .transformDeferred(CircuitBreakerOperator.of(circuitBreaker))
            .onErrorResume(failure -> fallbackItems(failure));
}
~~~

Ví dụ này dùng Resilience4j Reactor operator trực tiếp và cần dependency Reactor integration cùng một Circuit Breaker từ registry. Operator phải đứng trước `onErrorResume` để Circuit Breaker nhìn thấy lỗi trước khi fallback biến lỗi thành publisher thay thế. Với luồng đã phát một phần dữ liệu rồi mới lỗi, các phần tử đã gửi không thể thu hồi; API cần xác định rõ liệu có tiếp tục bằng dữ liệu dự phòng, kết thúc bằng lỗi hay đánh dấu luồng không đầy đủ.

## 10. Theo dõi trạng thái và metrics

Để đánh giá Circuit Breaker reactive, theo dõi các số liệu:

- Trạng thái từng instance: CLOSED, OPEN hoặc HALF_OPEN.
- Số lời gọi thành công, thất bại, chậm và bị từ chối.
- Failure rate và slow call rate so với ngưỡng cấu hình.
- Số lần fallback được gọi và tỷ lệ fallback thất bại.
- Độ trễ của publisher chính và thời gian trả kết quả cuối cùng.
- Số request bị hủy hoặc timeout nếu hệ thống có ghi nhận riêng.

Spring Cloud CircuitBreaker kết hợp Resilience4j có thể xuất metrics qua Micrometer khi ứng dụng bật cấu hình phù hợp. Có thể dùng Spring Boot Actuator và hệ thống thu thập metrics để quan sát instance `inventory`. Khi đọc dashboard, hãy phân biệt lỗi HTTP do dịch vụ phụ thuộc với lỗi từ chối do mạch OPEN.

Nếu API ngoài cùng vẫn trả kết quả thành công nhưng số lần fallback tăng, dịch vụ phụ thuộc có thể đang suy giảm. Cần hiển thị trạng thái dữ liệu dự phòng hoặc đánh dấu dữ liệu cache cũ để tầng giao diện và vận hành hiểu đúng kết quả.

## 11. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Tạo Circuit Breaker với tên không khớp cấu hình | Instance dự kiến không được áp dụng | Đối chiếu tên trong `create(...)` với `instances` |
| Không truyền publisher của WebClient vào `run` | Circuit Breaker không bọc lời gọi cần bảo vệ | Đưa publisher chính vào `run` |
| Dùng `block()` trong service reactive | Chặn luồng và làm giảm khả năng mở rộng | Trả `Mono` hoặc `Flux` cho tầng gọi |
| Xử lý lỗi thành giá trị trước Circuit Breaker | Circuit Breaker có thể ghi nhận thành công | Để lỗi truyền đến `run` và dùng fallback của Circuit Breaker |
| Fallback trả kiểu publisher không tương thích | Không biên dịch hoặc không khớp API | Trả `Mono<T>` hoặc `Flux<T>` đúng kiểu |
| Coi `Flux.empty()` luôn là fallback an toàn | Che giấu việc phụ thuộc không khả dụng | Dùng kết quả có trạng thái rõ ràng hoặc phát lỗi phù hợp |
| Chỉ cấu hình slow call threshold mà không có timeout | Lời gọi treo có thể giữ tài nguyên quá lâu | Cấu hình timeout ở publisher hoặc HTTP client |
| Không theo dõi fallback | API có thể trông khỏe trong khi phụ thuộc đang lỗi | Ghi metrics fallback và trạng thái Circuit Breaker |

## 12. Quy trình tích hợp

Khi bảo vệ một lời gọi WebClient, có thể thực hiện theo các bước:

1. Chọn tên Circuit Breaker ổn định cho phụ thuộc, ví dụ `inventory`.
2. Khai báo instance tương ứng trong cấu hình Resilience4j.
3. Inject `ReactiveCircuitBreakerFactory` và `WebClient` vào gateway hoặc service.
4. Tạo publisher chính bằng `retrieve()` hoặc `exchangeToMono()`, xử lý status lỗi thành exception phù hợp.
5. Gọi `factory.create(name)` và truyền publisher cùng fallback vào `ReactiveCircuitBreaker.run`.
6. Trả publisher cho tầng gọi; tránh `block()` và `subscribe()` thủ công trong service.
7. Kiểm tra thành công, HTTP 5xx, timeout, mạch OPEN và fallback; quan sát metrics để xác nhận Circuit Breaker ghi nhận đúng.

Bao WebClient bằng `ReactiveCircuitBreakerFactory` giúp đưa lời gọi HTTP vào cùng cơ chế bảo vệ với các thao tác đồng bộ, đồng thời giữ nguyên mô hình reactive. Khi publisher chính, chuyển đổi HTTP status, timeout và fallback được đặt đúng vị trí, Circuit Breaker có thể ghi nhận lỗi của phụ thuộc, mở mạch khi cần và thử phục hồi có kiểm soát mà không chặn luồng xử lý.
