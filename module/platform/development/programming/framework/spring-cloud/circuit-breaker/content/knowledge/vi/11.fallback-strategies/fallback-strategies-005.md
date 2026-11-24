# Phân biệt fallback cho lỗi gọi, timeout và mạch đang mở

Fallback là cách ứng dụng tạo phản hồi thay thế khi lời gọi được bảo vệ không thể cung cấp kết quả bình thường. Trong Spring Cloud Circuit Breaker với Resilience4j, fallback nhận `Throwable` gây ra tình huống cần phục hồi. Vì nhiều nguyên nhân khác nhau có thể kích hoạt fallback, ứng dụng nên phân loại nguyên nhân trước khi chọn dữ liệu dự phòng hoặc quyết định truyền lỗi lên caller.

Ba trường hợp cần phân biệt là lỗi từ dịch vụ phụ thuộc, timeout và Circuit Breaker từ chối lời gọi khi đang `OPEN`. Chúng có ý nghĩa vận hành khác nhau: lỗi gọi cho biết dependency đã trả lỗi hoặc kết nối thất bại; timeout cho biết kết quả đến quá muộn; mạch mở cho biết ứng dụng chủ động không gửi request vì đã phát hiện rủi ro hoặc hết quyền thăm dò ở `HALF_OPEN`.

## 1. Nhận diện nguyên nhân trước khi fallback

| Nguyên nhân | Exception thường gặp | Điều đã xảy ra | Hướng xử lý thường dùng |
| --- | --- | --- | --- |
| Lỗi từ dịch vụ phụ thuộc | `HttpServerErrorException`, `WebClientResponseException`, `ResourceAccessException`, exception nghiệp vụ | Request đã được gửi hoặc kết nối đã được thử; dependency trả lỗi hoặc không kết nối được | Dùng cache hợp lệ, kết quả một phần hoặc báo dependency không khả dụng |
| Timeout của TimeLimiter | `TimeoutException` | Lời gọi được bảo vệ không hoàn tất trong thời hạn cấu hình | Dùng dữ liệu cache gần nhất, phản hồi trạng thái chưa xác định hoặc trả lỗi timeout |
| Timeout từ HTTP client | Ví dụ `SocketTimeoutException` nằm trong `ResourceAccessException` hoặc `WebClientRequestException` | Tầng client đã hết thời gian chờ kết nối/response | Xử lý như lỗi giao tiếp, đồng thời kiểm tra timeout của client |
| Circuit Breaker từ chối | `CallNotPermittedException` | Mạch đang `OPEN`, hoặc `HALF_OPEN` đã cấp hết số quyền thăm dò | Fallback nhanh, cache cục bộ hoặc trả trạng thái tạm thời không khả dụng |
| Bulkhead hết sức chứa | `BulkheadFullException` từ SemaphoreBulkhead hoặc ThreadPoolBulkhead | Hệ thống không còn slot hoặc queue để nhận thêm tác vụ | Từ chối sớm, dùng cache cục bộ nếu an toàn hoặc báo quá tải |

`CallNotPermittedException` không có nghĩa dependency vừa trả lỗi trong request hiện tại. Circuit Breaker từ chối trước khi lời gọi tới dependency được thực hiện. Trong `HALF_OPEN`, exception này cũng có thể xuất hiện khi số lời gọi thăm dò được phép đã được sử dụng hết.

Không gộp timeout của TimeLimiter và timeout của HTTP client thành một nguyên nhân duy nhất. TimeLimiter giới hạn thời gian ở tầng thực thi được bảo vệ; HTTP client có thể timeout khi mở kết nối hoặc chờ dữ liệu. Exception và cách hủy tác vụ có thể khác nhau. Hãy kiểm tra chuỗi `cause` để biết tầng nào đã hết hạn.

## 2. Chọn fallback theo ý nghĩa nghiệp vụ

Giả sử ứng dụng quản lý tồn kho và cần gọi `inventory-service` để lấy số lượng của một SKU. Mỗi loại lỗi nên có chính sách riêng:

- **Lỗi gọi hoặc lỗi 5xx:** nếu cache có dữ liệu còn trong giới hạn tuổi cho phép, trả dữ liệu cache kèm thời điểm cập nhật. Nếu không có cache, trả trạng thái tồn kho chưa xác định hoặc lỗi dịch vụ không khả dụng.
- **Timeout:** ưu tiên dữ liệu cache gần nhất nếu nghiệp vụ chấp nhận dữ liệu cũ. Nếu dữ liệu cũ có thể gây quyết định sai, trả trạng thái chưa xác định thay vì giả định số lượng bằng 0.
- **Mạch đang mở:** phản hồi nhanh bằng cache hoặc trạng thái tạm thời không khả dụng. Không gọi lại cùng dependency từ fallback vì Circuit Breaker đã từ chối để bảo vệ hệ thống.
- **Bulkhead đầy:** xem đây là tín hiệu quá tải ở ứng dụng hoặc dependency. Không xếp thêm tác vụ vào một queue khác không giới hạn; có thể trả kết quả cache hoặc từ chối sớm.
- **Lỗi nghiệp vụ như SKU không tồn tại:** thường nên giữ nguyên lỗi 4xx hoặc exception nghiệp vụ. Không nên đổi lỗi đầu vào thành dữ liệu dự phòng khiến caller tưởng SKU hợp lệ.

Fallback phải tuân theo hợp đồng dữ liệu của API. Nếu trả dữ liệu cache, hãy biểu diễn nguồn dữ liệu và thời điểm cập nhật để caller biết đó là dữ liệu cũ. Nếu không có giá trị đáng tin cậy, trả lỗi rõ ràng thường an toàn hơn một giá trị mặc định có vẻ hợp lệ.

## 3. Phân loại exception với Spring Cloud CircuitBreaker factory

`CircuitBreakerFactory.create(id).run(supplier, fallback)` nhận một `Supplier<T>` và một `Function<Throwable, T>`. Function fallback được truyền exception đã kích hoạt fallback. Có thể phân loại exception ngay trong Function:

```java
public Stock getStock(String sku) {
    return circuitBreakerFactory.create("inventory").run(
            () -> inventoryClient.getStock(sku),
            error -> inventoryFallback(sku, error)
    );
}

private Stock inventoryFallback(String sku, Throwable error) {
    Throwable cause = unwrapAsyncWrapper(error);

    if (cause instanceof CallNotPermittedException) {
        return stockCache.findFreshEnough(sku)
                .orElseGet(() -> Stock.unavailable(sku, "CIRCUIT_OPEN"));
    }

    if (cause instanceof TimeoutException) {
        return stockCache.findFreshEnough(sku)
                .orElseGet(() -> Stock.unavailable(sku, "TIMEOUT"));
    }

    if (cause instanceof HttpServerErrorException
            || cause instanceof ResourceAccessException) {
        return stockCache.findFreshEnough(sku)
                .orElseGet(() -> Stock.unavailable(sku, "DEPENDENCY_ERROR"));
    }

    if (cause instanceof HttpClientErrorException clientError) {
        throw clientError; // Giữ nguyên lỗi nghiệp vụ/đầu vào 4xx
    }

    throw new InventoryLookupException("Không thể lấy tồn kho", cause);
}
```

`inventoryClient`, `stockCache` và các kiểu `Stock` là thành phần của ứng dụng minh họa. Đoạn mã cần các import Spring/Resilience4j tương ứng, gồm `CallNotPermittedException`, `HttpServerErrorException`, `HttpClientErrorException`, `ResourceAccessException` và `TimeoutException`.

Với lời gọi bất đồng bộ, exception có thể được bọc trong `CompletionException` hoặc `ExecutionException`. Có thể bỏ các lớp bọc này trước khi phân loại:

```java
private Throwable unwrapAsyncWrapper(Throwable error) {
    Throwable current = error;
    while ((current instanceof CompletionException
            || current instanceof ExecutionException)
            && current.getCause() != null) {
        current = current.getCause();
    }
    return current;
}
```

Chỉ bỏ các wrapper đã biết. Không đi sâu toàn bộ chuỗi `cause` một cách mù quáng vì một exception nghiệp vụ có thể cố ý giữ exception khác làm nguyên nhân. Với WebClient, kiểm tra cả `WebClientResponseException` và `WebClientRequestException`; lỗi timeout ở tầng client có thể nằm sâu hơn trong cause.

Nếu fallback không nhận diện được loại lỗi, hãy ghi nhận nguyên nhân và truyền lỗi phù hợp lên caller. Không nên biến mọi `Throwable` thành phản hồi thành công vì lỗi lập trình, lỗi xác thực hoặc lỗi dữ liệu có thể bị che giấu.

## 4. Dùng nhiều fallback method với annotation

Resilience4j Spring Boot hỗ trợ `fallbackMethod` cho annotation `@CircuitBreaker`, `@TimeLimiter`, `@Bulkhead` và các aspect liên quan. Cơ chế chọn fallback hoạt động tương tự các nhánh `catch`: nếu có nhiều phương thức cùng tên, Resilience4j chọn phương thức có kiểu exception khớp cụ thể nhất.

```java
@Service
public class InventoryService {
    private final InventoryClient inventoryClient;
    private final StockCache stockCache;

    public InventoryService(InventoryClient inventoryClient, StockCache stockCache) {
        this.inventoryClient = inventoryClient;
        this.stockCache = stockCache;
    }

    @CircuitBreaker(name = "inventory", fallbackMethod = "stockFallback")
    public Stock getStock(String sku) {
        return inventoryClient.getStock(sku);
    }

    public Stock stockFallback(String sku, CallNotPermittedException error) {
        return stockCache.findFreshEnough(sku)
                .orElseGet(() -> Stock.unavailable(sku, "CIRCUIT_OPEN"));
    }

    public Stock stockFallback(String sku, TimeoutException error) {
        return stockCache.findFreshEnough(sku)
                .orElseGet(() -> Stock.unavailable(sku, "TIMEOUT"));
    }

    public Stock stockFallback(String sku, HttpServerErrorException error) {
        return stockCache.findFreshEnough(sku)
                .orElseGet(() -> Stock.unavailable(sku, "DEPENDENCY_ERROR"));
    }

    public Stock stockFallback(String sku, HttpClientErrorException error) {
        throw error;
    }

    public Stock stockFallback(String sku, Throwable error) {
        throw new InventoryLookupException("Không thể lấy tồn kho", error);
    }
}
```

Mỗi fallback method nằm trong cùng class với phương thức được bảo vệ, có cùng các tham số nghiệp vụ và thêm đúng một tham số exception ở cuối. Kiểu trả về phải tương thích với phương thức gốc. Có thể khai báo fallback tổng quát nhận `Throwable` làm nhánh cuối cùng, nhưng cần giữ nguyên lỗi không thuộc nhóm được phép phục hồi.

Với `@TimeLimiter`, phương thức được bảo vệ thường trả về `CompletionStage` hoặc `CompletableFuture`; fallback cũng phải trả kiểu bất đồng bộ tương thích. Ví dụ:

```java
@TimeLimiter(name = "inventory", fallbackMethod = "stockTimeoutFallback")
public CompletableFuture<Stock> getStockAsync(String sku) {
    return inventoryClient.getStockAsync(sku);
}

public CompletableFuture<Stock> stockTimeoutFallback(
        String sku, TimeoutException error) {
    return CompletableFuture.completedFuture(
            stockCache.findFreshEnough(sku)
                    .orElseGet(() -> Stock.unavailable(sku, "TIMEOUT"))
    );
}
```

Fallback method của annotation được thực thi như một bộ xử lý exception và không phụ thuộc riêng vào trạng thái hiện tại của Circuit Breaker. Vì vậy, nó có thể xử lý lỗi dependency khi mạch `CLOSED`, timeout hoặc `CallNotPermittedException` khi mạch từ chối lời gọi.

## 5. Fallback trong lời gọi reactive

Với WebFlux, dùng `ReactiveCircuitBreakerFactory` và trả về publisher fallback. Không gọi `.block()` trong fallback:

```java
public Mono<Stock> getStock(String sku) {
    Mono<Stock> request = webClient.get()
            .uri("/stock/{sku}", sku)
            .retrieve()
            .bodyToMono(Stock.class);

    return reactiveCircuitBreakerFactory.create("inventory").run(
            request,
            error -> {
                Throwable cause = unwrapAsyncWrapper(error);

                if (cause instanceof CallNotPermittedException) {
                    return stockCache.findFreshEnoughReactive(sku)
                            .switchIfEmpty(Mono.just(
                                    Stock.unavailable(sku, "CIRCUIT_OPEN")));
                }

                if (cause instanceof TimeoutException
                        || cause instanceof WebClientRequestException) {
                    return stockCache.findFreshEnoughReactive(sku)
                            .switchIfEmpty(Mono.just(
                                    Stock.unavailable(sku, "TIMEOUT_OR_NETWORK_ERROR")));
                }

                if (cause instanceof WebClientResponseException responseError
                        && responseError.getStatusCode().is5xxServerError()) {
                    return Mono.just(Stock.unavailable(sku, "DEPENDENCY_ERROR"));
                }

                return Mono.error(cause);
            }
    );
}
```

Fallback reactive phải trả `Mono<T>` hoặc `Flux<T>` phù hợp với publisher gốc. Dùng `Mono.defer` nếu cần trì hoãn thao tác đọc cache hoặc tạo fallback cho tới khi có subscription. Nếu fallback cũng phát lỗi, lỗi đó tiếp tục được truyền tới subscriber và WebFlux xử lý theo cơ chế lỗi của ứng dụng.

Đối với `Flux`, cần quyết định rõ fallback là phát một giá trị thay thế, phát dữ liệu cache, hay kết thúc luồng bằng `Flux.empty()`. Trả `Flux.empty()` có thể khiến caller hiểu rằng không có sự kiện nào xảy ra; chỉ dùng khi ngữ nghĩa đó đúng với hợp đồng API.

## 6. Timeout, mạch mở và lỗi gọi không giống nhau

Ba nguyên nhân có thể cùng trả một dữ liệu cache nhưng cần được theo dõi riêng:

- **Lỗi gọi:** dependency đã trả lỗi hoặc không thể kết nối. Circuit Breaker có thể ghi nhận lỗi theo `recordExceptions`, `ignoreExceptions` hoặc predicate đã cấu hình.
- **Timeout:** TimeLimiter hoặc HTTP client kết thúc thời gian chờ. Với TimeLimiter, kết quả thường là `TimeoutException`; với client, exception có thể là `SocketTimeoutException` hoặc wrapper riêng của thư viện.
- **Mạch mở:** Circuit Breaker không cấp quyền thực thi và ném `CallNotPermittedException`. Request bị từ chối không tạo thêm một lời gọi tới dependency.

Không nên Retry `CallNotPermittedException` ngay bên ngoài cùng Circuit Breaker trong một vòng lặp ngắn. Các lần thử tiếp theo vẫn bị từ chối cho tới khi trạng thái cho phép, làm tăng tải ở ứng dụng mà không kiểm tra được dependency. Nếu dùng Retry cho lỗi transient, hãy cấu hình loại exception có thể thử lại và đặt tổng thời gian retry trong deadline của request.

Nếu lỗi HTTP 4xx là lỗi nghiệp vụ dự kiến, cân nhắc cấu hình `ignoreExceptions` hoặc `recordFailurePredicate` để Circuit Breaker không tính chúng như sự cố dependency. Việc bỏ qua thống kê lỗi không có nghĩa phải nuốt exception; caller vẫn có thể nhận lỗi 4xx.

Fallback thành công không chứng minh dependency đã phục hồi. Hãy theo dõi riêng kết quả lời gọi gốc, trạng thái Circuit Breaker và số lần fallback. Khi mạch chuyển `HALF_OPEN`, chỉ các lời gọi thăm dò được cấp quyền mới cung cấp bằng chứng về khả năng phục hồi.

## 7. Thiết kế fallback an toàn

Fallback nên có giới hạn tài nguyên và đường phụ thuộc riêng:

- Dùng cache cục bộ hoặc dữ liệu snapshot đã được xác định tuổi tối đa; tránh gọi ngược chính dependency đang lỗi.
- Không tạo queue hoặc retry vô hạn bên trong fallback. Điều đó có thể biến một lỗi nhanh thành tình trạng tắc nghẽn kéo dài.
- Đặt timeout và giới hạn concurrency cho nguồn cache từ xa nếu fallback phụ thuộc vào dịch vụ khác.
- Phân biệt `unavailable`, `unknown`, `stale` và giá trị nghiệp vụ thực. Không dùng số 0 hoặc danh sách rỗng làm tín hiệu lỗi nếu chúng cũng là dữ liệu hợp lệ.
- Ghi rõ fallback được dùng vì `CALL_ERROR`, `TIMEOUT`, `CIRCUIT_OPEN` hay `BULKHEAD_FULL` để vận hành có thể chẩn đoán.

Với API HTTP, ứng dụng có thể ánh xạ kết quả dự phòng thành response nghiệp vụ, `503 Service Unavailable` khi không có dữ liệu thay thế đáng tin cậy, hoặc `504 Gateway Timeout` khi hết deadline. Quyết định phụ thuộc hợp đồng API; không phải fallback nào cũng cần trả HTTP 200.

## 8. Theo dõi fallback và trạng thái Circuit Breaker

Thêm Actuator và `resilience4j-micrometer` để quan sát số lời gọi thành công, thất bại, không được phép, timeout và số lần fallback. Dùng tag theo tên instance như `inventory` để phân biệt từng dependency.

Những tín hiệu nên theo dõi cùng nhau:

| Tín hiệu | Câu hỏi cần trả lời |
| --- | --- |
| Circuit Breaker state và not-permitted calls | Mạch đang mở hay hết quyền thăm dò? |
| Circuit Breaker failed calls | Dependency đang trả lỗi hay timeout được ghi nhận là lỗi? |
| TimeLimiter timeout count | Có bao nhiêu lời gọi vượt deadline? |
| Fallback count theo reason | Caller nhận dữ liệu dự phòng vì nguyên nhân nào? |
| Cache hit, tuổi dữ liệu cache | Fallback có cung cấp dữ liệu còn đáng tin cậy không? |
| Bulkhead rejected calls | Ứng dụng có đang hết sức chứa không? |

Log nên có correlation ID, breaker ID, loại exception và fallback reason. Tránh ghi nội dung nhạy cảm hoặc toàn bộ response body của dependency.

## 9. Kịch bản kiểm chứng

Dùng mock server để chủ động tạo từng tình huống và xác nhận fallback tương ứng:

1. Cho inventory service trả 500. Xác nhận fallback `DEPENDENCY_ERROR` chạy và Circuit Breaker ghi nhận lỗi theo cấu hình.
2. Cho server phản hồi chậm hơn `timeoutDuration`. Xác nhận fallback `TIMEOUT` chạy, TimeLimiter phát sự kiện timeout và caller nhận đúng kiểu kết quả.
3. Làm đủ số lời gọi lỗi để breaker chuyển sang `OPEN`. Gửi thêm request và xác nhận `CallNotPermittedException` kích hoạt fallback `CIRCUIT_OPEN` mà mock server không nhận request mới.
4. Đặt breaker ở `HALF_OPEN` và dùng hết số quyền thăm dò. Xác nhận lời gọi vượt số quyền bị từ chối cũng được phân loại là `CallNotPermittedException`.
5. Làm đầy Bulkhead để kiểm tra `BulkheadFullException`; xác nhận fallback quá tải không đưa thêm công việc vào cùng pool.
6. Cho inventory service trả 404. Xác nhận lỗi nghiệp vụ được giữ nguyên hoặc ánh xạ theo hợp đồng, không biến thành dữ liệu tồn kho cache ngoài ý muốn.
7. Làm fallback cache thất bại. Xác nhận lỗi fallback được truyền tới caller và có log/metric riêng.
8. Khôi phục dependency, chờ các lời gọi thăm dò thành công và xác nhận breaker về `CLOSED`; fallback count giảm khi request thật được phục vụ.

## 10. Lỗi thường gặp

- Dùng chung một fallback cho mọi exception và trả dữ liệu mặc định dù nguyên nhân là lỗi đầu vào hoặc lỗi lập trình.
- Xem `CallNotPermittedException` như lỗi vừa trả về từ dependency, dù request đã bị chặn trước khi gửi.
- Không phân biệt timeout của TimeLimiter với timeout của HTTP client.
- Bỏ qua wrapper `CompletionException`/`ExecutionException`, khiến fallback không nhận diện được nguyên nhân gốc.
- Dùng fallback gọi lại cùng dependency, tạo vòng lặp hoặc tiếp tục gây tải khi mạch đang mở.
- Retry `CallNotPermittedException` liên tục khi Circuit Breaker chưa cho phép request.
- Dùng fallback `Flux.empty()` trong khi API cần phân biệt không có dữ liệu với dependency không khả dụng.
- Không theo dõi số lần fallback riêng với số lần gọi thành công của dependency.

## Tài liệu tham khảo

- [Spring Cloud Commons – Circuit Breaker](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-circuitbreaker.html): `CircuitBreakerFactory.run`, `ReactiveCircuitBreakerFactory.run` và Function fallback nhận `Throwable`.
- [Resilience4j – Getting Started with Spring Boot 2 and 3](https://resilience4j.readme.io/docs/getting-started-3): fallback method, lựa chọn exception phù hợp nhất, annotation và metrics.
- [Spring Cloud CircuitBreaker – Configuring Resilience4J Circuit Breakers](https://docs.spring.io/spring-cloud-circuitbreaker/reference/spring-cloud-circuitbreaker-resilience4j.html): TimeLimiter, cấu hình instance, Bulkhead và fallback qua factory.
- [Resilience4j – CircuitBreaker](https://resilience4j.readme.io/docs/circuitbreaker): trạng thái, quyền thực thi, sliding window và sự kiện Circuit Breaker.
