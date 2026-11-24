# Ảnh hưởng của nhiều subscription tới số lần gọi và thống kê

## Mục tiêu

Trong Reactor, tạo một `Mono` hoặc `Flux` chưa đồng nghĩa với việc lời gọi HTTP đã chạy. Publisher chỉ thực thi khi có subscription. Một publisher có thể được subscribe nhiều lần; tùy cách tạo và chia sẻ publisher, mỗi subscription có thể tạo một request mới, dùng lại kết quả đã cache hoặc nhận dữ liệu từ một luồng đang phát. Khi publisher được bảo vệ bởi Spring Cloud CircuitBreaker, cách tổ chức subscription còn ảnh hưởng tới số giấy phép được cấp và số kết quả mà Circuit Breaker ghi nhận.

Sau bài học, bạn có thể:

- Phân biệt giai đoạn tạo publisher với giai đoạn subscription.
- Giải thích vì sao hai subscription vào một publisher cold thường tạo hai request và hai lượt đánh giá Circuit Breaker.
- Dự đoán ảnh hưởng của `cache()`, `share()` và vị trí đặt Circuit Breaker tới số request thực tế và số mẫu thống kê.
- Phân biệt retry bên trong và bên ngoài Circuit Breaker.
- Kiểm soát subscription không chủ ý, quan sát metric và kiểm thử hành vi với nhiều subscriber.

## Tạo publisher và thực thi publisher

Reactor tách hai giai đoạn:

1. **Assembly:** ứng dụng xây dựng chuỗi operator và nhận về một `Mono` hoặc `Flux`. Thông thường, các bước này chỉ mô tả công việc sẽ thực hiện.
2. **Subscription:** một subscriber đăng ký nhận tín hiệu. Publisher bắt đầu thực thi theo semantics của nguồn dữ liệu và các operator trong chuỗi.

Ví dụ:

```java
Mono<Product> product = webClient.get()
        .uri("/products/{id}", "p-100")
        .retrieve()
        .bodyToMono(Product.class);
```

Đoạn mã trên tạo một publisher. Request HTTP chưa được gửi chỉ vì biến `product` đã được gán. Khi có subscription, `WebClient` mới thực thi request. Với publisher cold như `Mono` được tạo từ lời gọi `WebClient`, mỗi subscription độc lập thường khởi chạy một request mới:

```java
product.subscribe(value -> log.info("Subscriber A: {}", value));
product.subscribe(value -> log.info("Subscriber B: {}", value));
```

Hai lệnh `subscribe` tạo hai subscription. Với publisher cold ở ví dụ, dịch vụ danh mục thường nhận hai request. Việc dùng lại cùng biến `product` không tự động chia sẻ kết quả giữa hai subscriber.

Một số nguồn là hot publisher hoặc đã được chia sẻ/cache. Chúng có thể phát cùng một luồng dữ liệu cho nhiều subscriber, hoặc subscriber đến muộn chỉ nhận những gì semantics của nguồn cho phép. Vì vậy, không thể suy ra số request mạng chỉ từ số biến `Mono`/`Flux`; cần xem publisher được tạo từ đâu và các operator chia sẻ/cache được đặt ở vị trí nào.

## Mỗi subscription đi qua Circuit Breaker như thế nào?

Với reactive integration, `ReactiveCircuitBreaker.run` nhận một publisher và một hàm fallback. Khi subscriber đăng ký vào publisher đã được bảo vệ, operator Circuit Breaker tham gia vào quá trình subscription. Với publisher cold, mỗi subscription thường tạo một lượt gọi độc lập: Circuit Breaker kiểm tra quyền cho phép, nguồn thực thi và kết quả được ghi nhận khi chuỗi kết thúc.

```java
ReactiveCircuitBreaker breaker = factory.create("catalog");

Mono<Product> protectedProduct = Mono.from(
        breaker.run(
                webClient.get()
                        .uri("/products/{id}", "p-100")
                        .retrieve()
                        .bodyToMono(Product.class),
                error -> Mono.just(Product.unavailable("p-100"))));
```

Nếu `protectedProduct` là publisher cold và được subscribe hai lần, thông thường sẽ có hai lượt đi qua Circuit Breaker và hai request tới dịch vụ. Mỗi lượt có thể tiêu thụ một quyền gọi, được ghi nhận là thành công/thất bại hoặc bị từ chối tùy trạng thái và kết quả.

Ví dụ, với `slidingWindowType: COUNT_BASED`, `slidingWindowSize: 10` và `minimumNumberOfCalls: 5`, năm subscription hoàn tất độc lập có thể tạo năm mẫu trong cửa sổ. Nếu cả năm đều thất bại và các exception được tính là lỗi, tỷ lệ lỗi là 100% sau khi đủ mẫu tối thiểu. Mạch có thể chuyển sang `OPEN` theo `failureRateThreshold`.

Ở `HALF_OPEN`, số subscription được cấp phép cũng chịu giới hạn `permittedNumberOfCallsInHalfOpenState`. Một publisher cold được subscribe nhiều lần có thể tiêu thụ nhiều probe. Khi hết quyền, những subscription tiếp theo có thể bị từ chối và đi vào fallback.

## Đặt subscription đúng nơi

Trong ứng dụng WebFlux, controller thường trả `Mono` hoặc `Flux` để framework thực hiện subscription. Không cần tự gọi `subscribe()` trong service rồi lại trả chính publisher đó cho controller:

```java
// Không nên: tạo một subscription phụ ngoài vòng đời do WebFlux quản lý.
public Mono<Product> findById(String id) {
    Mono<Product> result = callProtectedService(id);
    result.subscribe();
    return result;
}
```

Đoạn mã trên có thể tạo hai subscription: một subscription do service tự kích hoạt và một subscription do framework kích hoạt khi ghi response. Với nguồn cold, request có thể chạy hai lần; Circuit Breaker cũng có thể ghi nhận hai lượt gọi.

Hãy trả publisher cho tầng gọi và để framework quản lý vòng đời:

```java
public Mono<Product> findById(String id) {
    return callProtectedService(id);
}
```

Chỉ tự subscribe khi thực sự tạo một luồng xử lý độc lập có chủ đích, chẳng hạn tác vụ nền có lifecycle và cơ chế giám sát riêng. Khi đó cần xác định rõ ai quản lý lỗi, hủy subscription và backpressure.

## Mẫu triển khai với ReactiveCircuitBreakerFactory

Ví dụ gateway tạo Circuit Breaker một lần theo ID dependency. `Mono.defer` tạo chuỗi request cho từng subscription, còn `ReactiveCircuitBreaker.run` bảo vệ từng lượt thực thi:

```java
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreaker;
import org.springframework.cloud.client.circuitbreaker.ReactiveCircuitBreakerFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@Service
public class CatalogGateway {
    private final WebClient webClient;
    private final ReactiveCircuitBreaker catalogBreaker;

    public CatalogGateway(
            WebClient webClient,
            ReactiveCircuitBreakerFactory<?, ?> factory) {
        this.webClient = webClient;
        this.catalogBreaker = factory.create("catalog");
    }

    public Mono<Product> findById(String id) {
        return Mono.defer(() -> {
            Mono<Product> request = webClient.get()
                    .uri("/products/{id}", id)
                    .retrieve()
                    .bodyToMono(Product.class);

            return Mono.from(catalogBreaker.run(
                    request,
                    error -> Mono.just(Product.unavailable(id))));
        });
    }
}
```

`Product` và `Product.unavailable` là kiểu dữ liệu của ứng dụng. `Mono.defer` giúp mỗi subscription tạo publisher request mới và thực hiện lời gọi trong ranh giới được bảo vệ. Nếu subscriber A và B cùng subscribe vào kết quả `findById`, mỗi subscriber thường tạo một request độc lập và một lượt đánh giá Circuit Breaker.

Nếu tầng gọi chỉ cần một kết quả, hãy truyền publisher đi tiếp mà không tự subscribe nhiều lần. Nếu cần chia sẻ một request cho nhiều nơi tiêu thụ, hãy chọn rõ operator chia sẻ và vị trí đặt nó so với Circuit Breaker.

## Ảnh hưởng của cache() và vị trí đặt Circuit Breaker

`cache()` lưu tín hiệu kết thúc của publisher để subscriber sau nhận lại tín hiệu đã lưu thay vì kích hoạt lại nguồn upstream. Vị trí đặt `cache()` quyết định Circuit Breaker nhìn thấy một subscription hay nhiều subscription.

**Bảo vệ trước, cache sau:**

```java
Mono<Product> protectedCall = Mono.from(
        catalogBreaker.run(remoteCall,
                error -> Mono.just(Product.unavailable(id))))
        .cache();
```

Subscriber đầu tiên đi qua Circuit Breaker và thực thi request. Kết quả cuối cùng của chuỗi được cache. Subscriber tiếp theo nhận tín hiệu đã cache; chúng không tạo subscription mới lên Circuit Breaker và không tạo request mới. Với publisher này, Circuit Breaker thường ghi nhận một lượt gọi cho lần nạp cache.

**Cache nguồn trước, bảo vệ sau:**

```java
Mono<Product> cachedRemoteCall = remoteCall.cache();

Mono<Product> protectedCall = Mono.from(
        catalogBreaker.run(cachedRemoteCall,
                error -> Mono.just(Product.unavailable(id))));
```

Mỗi subscriber vào `protectedCall` vẫn đi qua Circuit Breaker. Tuy nhiên, `cachedRemoteCall` chỉ thực thi nguồn upstream một lần rồi phát lại tín hiệu đã cache. Vì vậy, có thể xảy ra tình huống Circuit Breaker ghi nhận nhiều subscription trong khi dịch vụ đích chỉ nhận một request mạng.

| Cách đặt | Số lượt qua Circuit Breaker khi có nhiều subscriber | Số lần thực thi nguồn cold điển hình |
|---|---:|---:|
| `breaker.run(source).cache()` | Một lượt khi cache được nạp. | Một request. |
| `breaker.run(source.cache())` | Một lượt cho mỗi subscriber. | Một request được chia sẻ. |
| `breaker.run(source)` không cache/share | Một lượt cho mỗi subscriber. | Một request cho mỗi subscriber. |

`cache()` cũng cache tín hiệu lỗi hoặc empty completion. Nếu nguồn phát lỗi một lần rồi lỗi đó được cache, các subscriber sau vẫn nhận lỗi đã lưu. Khi cache đặt trước Circuit Breaker, mỗi subscription có thể làm Circuit Breaker đánh giá lại tín hiệu lỗi cũ dù không có request mới tới dịch vụ. Khi cache đặt sau Circuit Breaker, fallback result cũng có thể trở thành tín hiệu được cache. Hãy chọn chính sách TTL, invalidation và phạm vi cache phù hợp; không dùng một cache không thời hạn cho dữ liệu cần cập nhật thường xuyên.

## Ảnh hưởng của share() và publish()

`share()` cho phép nhiều subscriber dùng chung việc subscribe tới nguồn upstream. Với `Flux`, việc kết nối và ngắt kết nối còn phụ thuộc số subscriber đang hoạt động và semantics của `refCount`; với `Mono`, tín hiệu kết thúc có thể được phát lại cho subscriber sau. Hành vi chi tiết cần được xác nhận theo kiểu publisher và phiên bản Reactor. `share()` không cung cấp chính sách TTL hoặc invalidation theo nghiệp vụ như một cache chuyên dụng.

Vị trí của `share()` cũng ảnh hưởng thống kê:

```java
// Circuit Breaker ở upstream của share: nhóm subscriber dùng chung một lượt bảo vệ.
Mono<Product> oneProtectedExecution = Mono.from(
        catalogBreaker.run(remoteCall, fallback)).share();

// Circuit Breaker ở downstream của share: mỗi subscriber đi qua breaker,
// còn nguồn upstream có thể được chia sẻ.
Mono<Product> sharedSource = remoteCall.share();
Mono<Product> protectedPerSubscriber = Mono.from(
        catalogBreaker.run(sharedSource, fallback));
```

Trong trường hợp đầu, các subscriber đồng thời chia sẻ một subscription tới publisher đã được bảo vệ; Circuit Breaker thường thấy một lượt gọi. Trong trường hợp thứ hai, mỗi subscriber đăng ký qua Circuit Breaker, nhưng nguồn `share()` có thể chỉ tạo một subscription upstream cho nhóm subscriber đang cùng hoạt động. Kết quả là số lượt đánh giá Circuit Breaker có thể lớn hơn số request mạng thực tế.

Hành vi của `share()` phụ thuộc kiểu publisher và thời điểm subscriber đến/rời đi. Với `Flux` dùng `refCount`, khi số subscriber giảm xuống dưới ngưỡng kết nối có thể bị ngắt; subscriber mới sau đó có thể tạo kết nối upstream mới. Với `Mono`, cần kiểm tra việc phát lại tín hiệu kết thúc trong phiên bản Reactor đang dùng. Nếu yêu cầu lưu kết quả theo TTL, làm mới hoặc invalidation rõ ràng, hãy dùng cơ chế cache có chính sách tương ứng thay vì dựa vào `share()`.

## Retry bên trong và bên ngoài Circuit Breaker

Vị trí đặt `retryWhen` xác định Circuit Breaker quan sát từng lần thử hay chỉ quan sát kết quả cuối của chuỗi retry.

**Retry ở ngoài Circuit Breaker:**

```java
Mono<Product> retriedOutside = Mono.from(
        catalogBreaker.run(remoteCall,
                error -> Mono.error(error)))
        .retryWhen(retrySpec);
```

Mỗi lần retry subscribe lại publisher được bảo vệ. Mỗi lần thử có thể tiêu thụ một quyền gọi và tạo một kết quả thống kê riêng. Nếu lần thử đầu tiên làm mạch chuyển `OPEN`, lần retry sau có thể bị từ chối ngay mà không gọi dịch vụ đích.

**Retry ở bên trong Circuit Breaker:**

```java
Mono<Product> retriedInside = Mono.from(
        catalogBreaker.run(
                remoteCall.retryWhen(retrySpec),
                error -> Mono.just(Product.unavailable(id))));
```

Circuit Breaker bao toàn bộ chuỗi retry và thường ghi nhận một kết quả cuối cùng cho subscription bên ngoài. Dịch vụ đích vẫn có thể nhận nhiều request do retry, nhưng Circuit Breaker chỉ quan sát kết quả cuối của chuỗi. Điều này có thể làm số request mạng lớn hơn số lời gọi Circuit Breaker ghi nhận.

| Vị trí retry | Circuit Breaker quan sát | Request tới dịch vụ đích |
|---|---|---|
| Ngoài `run` | Từng subscription/lần thử đi qua breaker. | Có thể nhiều request; lần sau có thể bị `OPEN` từ chối. |
| Trong supplier/publisher truyền vào `run` | Kết quả cuối của chuỗi retry cho mỗi subscription ngoài. | Có thể nhiều request trong một lượt breaker. |

Ví dụ dùng `Mono.error(error)` trong fallback để cho phép lỗi truyền ra và retry tiếp. Nếu fallback chuyển lỗi thành một giá trị thành công, `retryWhen` ở ngoài sẽ không retry vì chuỗi đã kết thúc thành công. Cần phối hợp số lần thử, backoff, timeout và ngưỡng Circuit Breaker; retry quá nhiều có thể khuếch đại tải khi dịch vụ đang phục hồi.

## Nhiều subscription trong flatMap và giới hạn đồng thời

Một chuỗi `flatMap` có thể tạo subscription tới publisher con cho nhiều phần tử:

```java
Flux<Product> products = ids.flatMap(
        id -> catalogGateway.findById(id),
        8);
```

Tham số `8` giới hạn số publisher con được subscribe đồng thời trong `flatMap` này. Nếu mỗi phần tử gọi một dependency và mỗi publisher con đi qua Circuit Breaker, từng subscription có thể tiêu thụ một quyền gọi. Giới hạn đồng thời ở `flatMap` giúp kiểm soát concurrency tại luồng này, nhưng không thay thế Bulkhead vì các đường gọi khác trong ứng dụng vẫn có thể dùng chung dependency.

Nếu cần giới hạn tổng số lời gọi đồng thời tới dependency, cấu hình Bulkhead phù hợp với implementation và mô hình reactive. Cần quan sát cả số subscription, số request thực tế, số lời gọi bị từ chối và số tác vụ đang chạy để xác định giới hạn nào đang có hiệu lực.

## Hủy subscription và thống kê

Một subscriber có thể hủy subscription trước khi publisher hoàn tất, ví dụ khi client ngắt kết nối hoặc operator timeout kết thúc luồng. Hủy không đồng nghĩa với một lời gọi thành công. Cách Circuit Breaker giải phóng quyền gọi hoặc ghi nhận cancellation phụ thuộc operator và phiên bản implementation; không tự cộng cancellation vào số thành công hay thất bại khi phân tích số liệu.

Nếu HTTP request đã được gửi, hủy subscription cũng không bảo đảm client hoặc máy chủ từ xa dừng công việc ngay lập tức. Cần cấu hình timeout ở HTTP client, kiểm tra khả năng cancel của connector và quan sát số request còn chạy sau khi subscriber đã hủy.

## Theo dõi subscription và Circuit Breaker

Với Resilience4j và Micrometer, các metric thường hữu ích gồm:

- `resilience4j.circuitbreaker.calls`: số lời gọi theo kết quả.
- `resilience4j.circuitbreaker.state`: trạng thái instance.
- `resilience4j.circuitbreaker.not.permitted.calls`: số subscription/lời gọi bị từ chối.
- `resilience4j.circuitbreaker.buffered.calls`: số kết quả được lưu trong cửa sổ thống kê.
- `resilience4j.circuitbreaker.failure.rate` và `resilience4j.circuitbreaker.slow.call.rate`: tỷ lệ dùng để đánh giá ngưỡng.

Tên metric và tag cụ thể có thể thay đổi theo phiên bản, registry và cấu hình. Nên bổ sung log hoặc trace ở các ranh giới sau:

- Khi publisher được tạo, ghi ID dependency và correlation ID nếu cần.
- Khi subscription bắt đầu, ghi một mã subscription riêng để phân biệt nhiều subscriber cùng dùng một publisher.
- Khi request HTTP thực sự được gửi, ghi endpoint logic và thời gian bắt đầu.
- Khi chuỗi kết thúc, ghi kết quả, lỗi, fallback, timeout hoặc cancellation.

Không ghi dữ liệu nhạy cảm hoặc token trong log. Khi so sánh số liệu, phân biệt ba con số: số subscription vào publisher được bảo vệ, số request thực tế tới dịch vụ phụ thuộc và số kết quả Circuit Breaker ghi nhận. Chúng có thể khác nhau khi dùng cache, share, retry hoặc fallback.

## Thực hành kiểm chứng nhiều subscription

Thực hiện trong môi trường thử nghiệm với một endpoint danh mục có thể quan sát số request:

1. Tạo một `Mono` cold bằng `WebClient` và bọc bằng `ReactiveCircuitBreaker.run`.
2. Subscribe hai lần vào cùng publisher. Đếm request ở dịch vụ đích và quan sát metric Circuit Breaker; với nguồn cold không chia sẻ, thường có hai request và hai lượt đánh giá.
3. Đặt `cache()` sau publisher đã được bảo vệ rồi subscribe hai lần. Xác nhận chỉ lần đầu đi qua Circuit Breaker và tạo request upstream.
4. Đặt `cache()` trước Circuit Breaker rồi subscribe hai lần. Xác nhận Circuit Breaker có thể ghi nhận hai lượt subscription trong khi nguồn HTTP chỉ chạy một lần.
5. Thử `share()` với cả `Mono` và `Flux`, gồm subscriber đồng thời và subscriber đến sau khi nguồn kết thúc; ghi nhận semantics replay/kết nối của phiên bản Reactor đang dùng.
6. Đặt `retryWhen` lần lượt ngoài và trong `run`; so sánh số request thực tế với số kết quả Circuit Breaker ghi nhận.
7. Hủy một subscription trước khi request hoàn tất; kiểm tra metric, log, khả năng hủy I/O và số request còn chạy.

Ghi lại số subscriber, số subscription, số request HTTP, số kết quả thành công/thất bại, số lần fallback và trạng thái Circuit Breaker. Dùng cùng một kịch bản khi thay đổi vị trí operator để thấy rõ thay đổi đến từ cách tổ chức luồng.

## Lỗi thường gặp

- **Cho rằng tạo Mono là đã gọi HTTP:** request thường chỉ chạy khi có subscription.
- **Subscribe cùng publisher cold nhiều lần:** mỗi subscriber có thể tạo một request mới và một lượt thống kê riêng.
- **Tự subscribe trong service rồi trả publisher:** có thể tạo subscription phụ ngoài subscription do WebFlux quản lý.
- **Đặt cache sai phía Circuit Breaker:** số request mạng và số mẫu thống kê có thể không còn tương ứng.
- **Dùng share thay cache có TTL:** `share()` không cung cấp chính sách hết hạn và invalidation theo nghiệp vụ; semantics replay/kết nối còn phụ thuộc Mono, Flux và phiên bản Reactor.
- **Retry ngoài breaker mà không tính số lần thử:** mỗi lần thử lại có thể tiêu thụ thêm quyền gọi và làm tăng mẫu thống kê.
- **Retry trong breaker nhưng chỉ nhìn metric Circuit Breaker:** một mẫu cuối có thể đại diện cho nhiều request mạng.
- **Coi cancellation là success:** subscription bị hủy cần được phân tích riêng theo hành vi operator.
- **Không giới hạn concurrency:** `flatMap` có thể tạo nhiều subscription đồng thời và gây áp lực lên dependency.

Khi làm việc với reactive stream, hãy xem subscription là điểm bắt đầu của một lượt thực thi. Xác định rõ mỗi subscriber có cần một request riêng hay cần chia sẻ kết quả, sau đó đặt `cache`, `share`, retry và Circuit Breaker theo đúng ngữ nghĩa mong muốn. Việc này giúp số liệu Circuit Breaker phản ánh đúng hành vi mà hệ thống cần bảo vệ.
