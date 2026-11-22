# Xử lý kết quả rỗng, lỗi từng dịch vụ và dữ liệu dự phòng trong Reactor

Một API tổng hợp thường gọi nhiều nguồn: catalog, inventory, pricing, recommendation, profile hoặc các microservice khác. Mỗi nguồn có thể trả dữ liệu, không tìm thấy dữ liệu, phát lỗi hoặc phản hồi quá thời hạn. Trong reactive pipeline, những tình huống này có semantics khác nhau. Nếu xem kết quả rỗng như lỗi, hoặc bắt mọi lỗi rồi trả dữ liệu mặc định, API có thể che giấu sự cố và tạo response trông có vẻ thành công nhưng sai ý nghĩa.

Reactor phân biệt ba trạng thái: publisher phát giá trị rồi hoàn tất, publisher hoàn tất mà không phát giá trị, và publisher kết thúc bằng lỗi. Các operator như defaultIfEmpty, switchIfEmpty, onErrorResume, timeout, retryWhen và zip giúp định nghĩa chính sách cho từng nguồn. Điều quan trọng là chọn đúng phạm vi: một dịch vụ phụ trợ có thể được thay bằng dữ liệu dự phòng trong khi dịch vụ bắt buộc vẫn phải làm request thất bại.

Bài học thuộc nhóm **Thực hành tổng hợp** của module Spring Framework - reactive. Bài đi từ semantics của Mono/Flux tới chiến lược tổng hợp nhiều dịch vụ, partial response, timeout/retry/fallback, ví dụ Spring Boot WebFlux hoàn chỉnh và kiểm thử bằng StepVerifier cùng WebTestClient.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt Mono có giá trị, Mono.empty() và Mono.error().
- Hiểu Flux.empty(), next(), single() và collectList() khi nguồn không phát phần tử.
- Dùng defaultIfEmpty() cho giá trị mặc định đơn giản.
- Dùng switchIfEmpty() để chuyển sang publisher dự phòng.
- Dùng Mono.defer() để trì hoãn việc tạo fallback.
- Phân biệt xử lý empty với xử lý error.
- Dùng onErrorReturn(), onErrorResume(), onErrorMap() và doOnError() đúng mục đích.
- Hiểu vì sao Mono.zip() không phát kết quả nếu một nguồn empty.
- Biết zipDelayError() trì hoãn lỗi nhưng không biến empty thành giá trị.
- Chuẩn hóa nguồn bắt buộc và nguồn tùy chọn trước khi zip.
- Thiết kế kết quả partial có trạng thái AVAILABLE, EMPTY hoặc FALLBACK.
- Đặt timeout và retry trước fallback theo đúng chính sách.
- Chỉ fallback cho lỗi có thể phục hồi.
- Kiểm soát cancellation và các lời gọi song song khi một nguồn thất bại.
- Tích hợp nhiều downstream bằng WebClient mà vẫn giữ reactive composition.
- Viết service aggregation và kiểm thử success, empty, error, timeout và not-found.

## 2. Ba trạng thái cơ bản của Publisher

Một Mono<T> có thể kết thúc theo ba cách:

| Trạng thái | Tín hiệu | Ý nghĩa |
| --- | --- | --- |
| Có giá trị | onNext(value), onComplete | Có dữ liệu |
| Rỗng | onComplete, không có onNext | Không có kết quả |
| Lỗi | onError(error) | Không hoàn thành thành công |

~~~java
Mono<String> found = Mono.just("product-1");
Mono<String> missing = Mono.empty();
Mono<String> failed = Mono.error(
    new IllegalStateException("catalog unavailable"));
~~~

Ba publisher không tương đương nhau:

- found phát một String.
- missing hoàn tất bình thường nhưng không phát String.
- failed kết thúc bằng lỗi.

Empty không nhất thiết là lỗi. Tìm một sản phẩm không tồn tại có thể là kết quả bình thường ở tầng repository; service nghiệp vụ sau đó mới quyết định chuyển nó thành 404. Ngược lại, timeout của catalog thường là lỗi hạ tầng và cần chính sách riêng.

Giả sử trang sản phẩm tổng hợp thông tin catalog, tồn kho và gợi ý. Catalog không tìm thấy sản phẩm có nghĩa trang không tồn tại. Inventory không có bản ghi có thể có nghĩa số lượng chưa được đồng bộ và giao diện nên hiển thị "chưa rõ". Recommendation lỗi có thể không ảnh hưởng khả năng xem sản phẩm; trang vẫn có thể hiển thị với danh sách gợi ý rỗng và trạng thái fallback.

## 3. Empty trong Mono và Flux

### Mono.empty()

Mono.empty() phát onComplete mà không có onNext:

~~~java
Mono<String> result = Mono.empty();

Mono<Integer> length = Mono.<String>empty()
    .map(String::length);
~~~

length cũng hoàn tất rỗng. map và flatMap cần một giá trị để gọi mapper; không có phần tử thì mapper không chạy.

### Flux.empty()

Flux.empty() cũng hoàn tất mà không phát phần tử:

~~~java
Flux<String> names = Flux.empty();
~~~

Các operator xử lý từng phần tử như map, filter và flatMap không được gọi vì không có phần tử đầu vào.

### next() và single()

Flux.next() lấy phần tử đầu tiên thành Mono. Nếu Flux rỗng, Mono kết quả cũng rỗng:

~~~java
Mono<String> first = Flux.<String>empty().next();
~~~

single() yêu cầu đúng một phần tử; nếu nguồn rỗng hoặc có nhiều hơn một phần tử, nó phát lỗi. singleOrEmpty() cho phép zero hoặc one element, nhưng vẫn lỗi nếu có nhiều hơn một phần tử.

### collectList() có semantics khác

~~~java
Mono<List<String>> list = Flux.<String>empty()
    .collectList();
~~~

Kết quả là Mono phát một List rỗng rồi complete, không phải Mono.empty(). Vì vậy Mono<Recommendation> có thể empty khi không có một recommendation, còn Flux<Recommendation>.collectList() thường phát List.of() khi không có recommendation.

## 4. defaultIfEmpty(): thay empty bằng một giá trị

defaultIfEmpty(T) phát giá trị dự phòng nếu upstream hoàn tất rỗng:

~~~java
Mono<String> name = repository.findName("p-404")
    .defaultIfEmpty("Unknown product");
~~~

Nếu repository phát "Notebook", kết quả vẫn là "Notebook". Nếu repository empty, kết quả là "Unknown product".

Dùng defaultIfEmpty khi fallback là giá trị đã biết, rẻ và không cần gọi thêm publisher:

~~~java
Mono<Integer> stock = inventory.findAvailable("p-1")
    .defaultIfEmpty(0);
~~~

Nhưng hãy cẩn trọng: 0 có thể có nghĩa "đã xác nhận hết hàng", trong khi empty có thể có nghĩa "không có bản ghi tồn kho". Nếu hai ý nghĩa khác nhau, dùng model có trạng thái thay vì thay empty thành 0 một cách mù quáng.

defaultIfEmpty không xử lý lỗi:

~~~java
Mono<String> result = Mono.<String>error(
        new IllegalStateException("network failed"))
    .defaultIfEmpty("fallback");
~~~

Publisher vẫn phát error. defaultIfEmpty chỉ xử lý onComplete không có onNext, không xử lý onError. Reactor cũng không cho Mono.just(null) hoặc defaultIfEmpty(null); nếu domain cần biểu diễn không có giá trị, dùng Optional hoặc record trạng thái.

## 5. switchIfEmpty(): chuyển sang publisher dự phòng

switchIfEmpty(Publisher<T>) đăng ký publisher thay thế nếu nguồn ban đầu hoàn tất rỗng:

~~~java
Mono<Product> product = cache.findById(id)
    .switchIfEmpty(database.findById(id));
~~~

Luồng:

~~~text
cache.findById(id)
      |
      +-- có product ---------> phát product
      |
      +-- empty --------------> subscribe database.findById(id)
                                   |
                                   +-- có product -> phát product
                                   +-- empty -> empty
                                   +-- error -> error
~~~

Đây là pattern cache-aside: cache miss chuyển sang database. Nếu cache phát error, switchIfEmpty không chạy; cần quyết định riêng liệu lỗi cache có nên được fallback sang database hay không.

~~~java
Mono<Product> product = cache.findById(id)
    .onErrorResume(
        CacheUnavailableException.class,
        error -> Mono.empty())
    .switchIfEmpty(
        Mono.defer(() -> database.findById(id)));
~~~

Đoạn này chủ động xem cache outage như cache miss. Chính sách chỉ hợp lý nếu database là nguồn sự thật và cache chỉ là tối ưu. Hãy ghi log/metric lỗi cache để outage không bị che khuất.

### Dùng Mono.defer() để trì hoãn fallback

Nếu database.findById(id) có side effect đồng bộ ngay khi method được gọi, publisher có thể được tạo dù cache có dữ liệu. Để bảo đảm fallback chỉ được khởi tạo khi cần:

~~~java
Mono<Product> product = cache.findById(id)
    .switchIfEmpty(
        Mono.defer(() -> database.findById(id)));
~~~

Mono.defer gọi supplier khi fallback được subscribe. Nó cũng giúp chuyển exception phát đồng bộ khi gọi method thành onError trong reactive chain.

Defer không trì hoãn publisher đã được tạo sẵn:

~~~java
Mono<Product> alreadyBuilt = database.findById(id);

Mono<Product> wrong = cache.findById(id)
    .switchIfEmpty(Mono.defer(() -> alreadyBuilt));
~~~

Ở đây supplier vẫn trả publisher đã tạo trước. Hãy đặt việc gọi gateway vào supplier.

## 6. Biến empty thành lỗi ở nguồn bắt buộc

Một số nguồn là bắt buộc. Ví dụ catalog phải có sản phẩm mới được phép xây trang chi tiết. Repository có thể trả Mono.empty(), nhưng service cần chuyển nó thành lỗi domain:

~~~java
Mono<Product> requiredProduct =
    catalog.findById(id)
        .switchIfEmpty(Mono.error(
            new ProductNotFoundException(id)));
~~~

Điều này làm semantics rõ ràng:

- Catalog có product: tiếp tục.
- Catalog empty: ProductNotFoundException.
- Catalog error: lỗi được giữ nguyên hoặc được map theo chính sách.

Không nên dùng defaultIfEmpty(new Product(...)) nếu sản phẩm không tồn tại phải trả 404. Dữ liệu giả sẽ làm API hiển thị một tài nguyên không có thật.

Controller có thể ánh xạ domain error:

~~~java
@ExceptionHandler(ProductNotFoundException.class)
public ResponseEntity<ApiError> notFound(
        ProductNotFoundException error) {
    return ResponseEntity.status(HttpStatus.NOT_FOUND)
        .body(new ApiError("PRODUCT_NOT_FOUND", error.getMessage()));
}
~~~

Đây là fragment controller; phần sample hoàn chỉnh phía dưới có code và test HTTP.

## 7. onErrorReturn(): fallback bằng một giá trị cố định

onErrorReturn(T) thay lỗi bằng một giá trị tĩnh:

~~~java
Mono<ExchangeRate> rate = exchangeGateway.getRate("USD", "VND")
    .onErrorReturn(ExchangeRate.unavailable());
~~~

Nó đơn giản nhưng có nhược điểm: không phân biệt timeout, authentication, validation hoặc programming error nếu dùng overload bắt mọi Throwable. Dùng overload có kiểu lỗi nếu chỉ muốn xử lý một nhóm cụ thể:

~~~java
Mono<ExchangeRate> rate = exchangeGateway.getRate("USD", "VND")
    .onErrorReturn(
        DownstreamUnavailableException.class,
        ExchangeRate.unavailable());
~~~

Không fallback mọi lỗi thành giá trị mặc định nếu một lỗi 401, 403 hoặc lỗi mapping cần được xử lý riêng.

## 8. onErrorResume(): chuyển lỗi sang publisher khác

onErrorResume cho phép lựa chọn publisher thay thế dựa trên exception:

~~~java
Mono<Profile> profile = profileClient.find(userId)
    .onErrorResume(
        ProfileServiceUnavailableException.class,
        error -> profileCache.find(userId));
~~~

Fallback có thể gọi cache, database hoặc một service khác.

~~~java
// Fallback cho mọi lỗi.
source.onErrorResume(error -> fallback());

// Fallback chỉ cho một kiểu lỗi.
source.onErrorResume(
    TimeoutException.class,
    error -> cachedValue());

// Fallback theo predicate.
source.onErrorResume(
    this::isRecoverable,
    error -> fallback());
~~~

Chỉ chọn lỗi có thể phục hồi. Ví dụ timeout của recommendation có thể cho phép trả danh sách rỗng; IllegalArgumentException do code gọi sai không nên bị biến thành "không có recommendation".

onErrorResume không xử lý empty:

~~~java
Mono<String> value = Mono.<String>empty()
    .onErrorResume(error -> Mono.just("fallback"));
~~~

value vẫn empty. Muốn xử lý empty, thêm switchIfEmpty hoặc defaultIfEmpty.

### Ghi nhận trước khi fallback

~~~java
Mono<Profile> profile = profileClient.find(userId)
    .onErrorResume(
        ProfileServiceUnavailableException.class,
        error -> {
            log.warn("Profile service unavailable; using cache");
            return profileCache.find(userId);
        });
~~~

Không ghi raw token hoặc payload nhạy cảm. Nên ghi service name, error category và trace ID đã được kiểm soát.

## 9. doOnError, onErrorMap và onErrorComplete

### doOnError(): side effect quan sát lỗi

~~~java
Mono<Product> product = catalog.findById(id)
    .doOnError(error ->
        log.error("Catalog lookup failed", error));
~~~

doOnError không phục hồi. Error vẫn đi xuống downstream.

### onErrorMap(): chuyển loại lỗi

~~~java
Mono<Product> product = catalog.findById(id)
    .onErrorMap(
        WebClientRequestException.class,
        error -> new CatalogUnavailableException(error));
~~~

Dùng khi cần chuyển lỗi kỹ thuật thành lỗi domain hoặc lỗi thống nhất của application. Giữ nguyên cause để điều tra.

### onErrorComplete(): nuốt lỗi thành empty

~~~java
Mono<Recommendation> recommendations =
    recommendationClient.find(id)
        .onErrorComplete();
~~~

Nó biến error thành completion rỗng. Cách này có thể làm pipeline trông thành công và mất thông tin nguyên nhân. Nếu dùng, cần logging/metrics rõ ràng và chỉ áp dụng với nguồn thực sự optional. Thường một record trạng thái FALLBACK dễ quan sát hơn empty hoàn toàn.

onErrorContinue không phải fallback tổng quát: semantics phụ thuộc operator upstream và có thể làm luồng lỗi khó hiểu. Với aggregation nhiều dịch vụ, ưu tiên xử lý lỗi ngay trên từng publisher bằng onErrorResume.

## 10. Mono.zip(): tổng hợp nhiều nguồn có giá trị

Mono.zip đợi mỗi nguồn phát một phần tử, rồi gọi combinator:

~~~java
Mono<ProductView> view = Mono.zip(
    catalog.findById(id),
    inventory.findByProductId(id),
    recommendations.findByProductId(id),
    ProductView::new);
~~~

Nếu cả ba nguồn phát dữ liệu, ProductView được tạo. Nếu một nguồn phát error, zip kết thúc bằng error và có thể cancel các nguồn còn lại. Nếu một nguồn complete empty, zip hoàn tất empty vì không thể tạo tuple có đủ giá trị. Combinator không được gọi.

### Ví dụ nguy hiểm

~~~java
Mono<String> name = Mono.just("Notebook");
Mono<Integer> stock = Mono.empty();

Mono<ProductSummary> summary =
    Mono.zip(name, stock, ProductSummary::new);
~~~

summary không phát ProductSummary; nó complete empty.

### Chuẩn hóa nguồn trước khi zip

Nếu inventory là optional, chuyển empty thành một section có trạng thái:

~~~java
Mono<InventorySection> stock = inventory.findByProductId(id)
    .map(InventorySection::available)
    .switchIfEmpty(Mono.just(
        InventorySection.unknown()));

Mono<ProductSummary> summary =
    Mono.zip(
        catalog.findById(id),
        stock,
        ProductSummary::new);
~~~

Nếu inventory error cũng có thể phục hồi:

~~~java
Mono<InventorySection> stock = inventory.findByProductId(id)
    .map(InventorySection::available)
    .switchIfEmpty(Mono.just(InventorySection.unknown()))
    .onErrorResume(
        InventoryUnavailableException.class,
        error -> Mono.just(InventorySection.unavailable()));
~~~

Bây giờ stock luôn phát một InventorySection trong ba trạng thái success, empty hoặc fallback. ProductSummary có thể được tạo nếu catalog bắt buộc phát product.

## 11. zipDelayError(): trì hoãn lỗi không có nghĩa là fallback

Mono.zipDelayError khác Mono.zip ở cách xử lý lỗi:

- Mono.zip thường kết thúc sớm khi một nguồn error hoặc empty.
- Mono.zipDelayError trì hoãn error để các nguồn còn lại có cơ hội hoàn tất.
- Nếu một nguồn empty, kết quả cuối vẫn empty sau khi các nguồn còn lại hoàn tất.
- Nếu nhiều nguồn error, Reactor có thể kết hợp các exception dưới dạng suppressed exceptions.

~~~java
Mono.zipDelayError(
    catalog.findById(id),
    inventory.findByProductId(id),
    ProductView::new);
~~~

zipDelayError không thay empty bằng giá trị mặc định. Nó cũng không tự biến lỗi inventory thành partial result. Dùng zipDelayError khi cần chờ các nguồn khác hoàn tất để quan sát lỗi đồng thời; dùng onErrorResume/defaultIfEmpty/switchIfEmpty để định nghĩa fallback.

## 12. Mono<Void> không phù hợp làm một phần tử của zip

Mono<Void> biểu diễn một thao tác chỉ có completion, không có giá trị. Vì vậy nó luôn empty đối với operator cần một element:

~~~java
Mono<Void> audit = auditService.record(event);

Mono<Result> wrong = Mono.zip(
    catalog.findById(id),
    audit,
    Result::new);
~~~

combinator không thể nhận một giá trị từ audit. Hãy compose side effect trước rồi trả lại giá trị cần thiết:

~~~java
Mono<Product> product = catalog.findById(id)
    .flatMap(found ->
        auditService.record(found)
            .thenReturn(found));
~~~

Hoặc nếu cần chạy hai tác vụ độc lập rồi tiếp tục:

~~~java
Mono<Product> product = catalog.findById(id);
Mono<Void> audit = auditService.recordRequest(id);

Mono<Product> result = product
    .delayUntil(ignored -> audit);
~~~

Nếu chỉ cần chờ nhiều side effect hoàn tất, dùng Mono.when:

~~~java
Mono<Void> completed = Mono.when(
    auditService.record(event),
    eventBus.publish(event));
~~~

Nếu cần giữ giá trị nghiệp vụ sau side effect:

~~~java
Mono<Order> result = repository.save(order)
    .flatMap(saved ->
        Mono.when(
            auditService.record(saved),
            eventBus.publish(saved))
        .thenReturn(saved));
~~~

## 13. Mô hình partial result: phân biệt EMPTY và FALLBACK

Trong trang tổng hợp, một số dữ liệu bắt buộc và một số dữ liệu tùy chọn.

| Nguồn | Empty | Error | Chính sách mẫu |
| --- | --- | --- | --- |
| Catalog | Không có sản phẩm | Catalog lỗi | Empty thành 404; error propagate hoặc map 503 |
| Inventory | Chưa có bản ghi | Timeout/service lỗi | Trả trạng thái EMPTY hoặc FALLBACK |
| Recommendations | Không có gợi ý | Service lỗi | Trả list rỗng với trạng thái tương ứng |
| Pricing | Không có giá | Pricing lỗi | Tùy nghiệp vụ: chặn mua hoặc dùng giá cache được xác minh |
| Reviews | Không có review | Service lỗi | Có thể hiển thị list rỗng và trạng thái fallback |

Một model rõ ràng:

~~~java
public enum SectionStatus {
    AVAILABLE,
    EMPTY,
    FALLBACK
}

public record Section<T>(
    SectionStatus status,
    T value,
    String reason) {
}
~~~

Ví dụ response:

~~~json
{
  "product": {
    "id": "p-1",
    "name": "Notebook"
  },
  "inventory": {
    "status": "EMPTY",
    "value": {
      "available": 0,
      "known": false
    },
    "reason": null
  },
  "recommendations": {
    "status": "FALLBACK",
    "value": [],
    "reason": "recommendations_unavailable"
  }
}
~~~

Consumer hiểu rằng inventory chưa được xác định, còn recommendation list rỗng do service lỗi. Nếu chỉ trả 0 và [] mà không có trạng thái, consumer có thể hiểu sai rằng hàng đã hết và không có gợi ý nào tồn tại.

Optional<T> có thể diễn tả có/không có một giá trị đơn giản, nhưng không phân biệt "không có bản ghi" với "downstream bị timeout". Nếu cần status và reason, dùng wrapper record như Section<T>.

## 14. Xử lý fallback theo từng dịch vụ

Một aggregation tốt đặt policy ngay trên publisher của từng downstream.

~~~java
Mono<Section<Inventory>> inventorySection =
    inventoryGateway.findByProductId(id)
        .timeout(Duration.ofMillis(300))
        .map(Section::available)
        .switchIfEmpty(Mono.just(
            Section.empty(Inventory.unknown())))
        .onErrorResume(
            this::isRecoverable,
            error -> Mono.just(
                Section.fallback(
                    Inventory.unknown(),
                    safeReason(error))));
~~~

Thứ tự có ý nghĩa:

1. Gọi downstream.
2. timeout giới hạn thời gian chờ.
3. map dữ liệu thành section AVAILABLE.
4. switchIfEmpty xử lý hoàn tất rỗng.
5. onErrorResume xử lý timeout hoặc lỗi recoverable.

Một error không bị switchIfEmpty xử lý. Một empty không bị onErrorResume xử lý. Chính sách rõ ràng cho cả hai trạng thái.

Không bắt mọi lỗi:

~~~java
.onErrorResume(error ->
    Mono.just(Section.fallback(defaultValue, "failed")))
~~~

Cách này có thể che NullPointerException, lỗi mapping hoặc bug trong code. Tốt hơn là kiểm tra error instanceof TimeoutException hoặc một exception domain cụ thể, rồi chỉ fallback cho nhóm recoverable.

## 15. Timeout, retry và fallback: thứ tự quan trọng

Một request downstream có thể chậm, lỗi tạm thời hoặc hoàn tất rỗng. Chính sách thường gồm timeout, retry có giới hạn, rồi fallback.

~~~java
Mono<Inventory> inventory =
    Mono.defer(() -> inventoryGateway.findByProductId(id))
        .timeout(Duration.ofMillis(250))
        .retryWhen(
            Retry.backoff(1, Duration.ofMillis(30))
                .filter(this::isTransient))
        .onErrorResume(
            this::isRecoverable,
            error -> Mono.just(Inventory.unknown()));
~~~

### Vì sao retry trước fallback?

Nếu fallback được áp dụng trước retry:

~~~java
source
    .onErrorResume(error -> Mono.just(defaultValue))
    .retryWhen(Retry.max(2));
~~~

error đã bị chuyển thành onNext(defaultValue), nên retry không còn nhận lỗi để thực hiện.

Thứ tự thường dùng:

~~~text
Downstream call
      |
      v
Timeout
      |
      v
Retry transient error (bounded)
      |
      v
Fallback recoverable error
      |
      v
Aggregate result
~~~

### Empty có nên retry?

Thông thường không. Empty là completion thành công không có giá trị, không phải lỗi tạm thời. retryWhen chỉ xử lý error signal; nó không retry khi source complete empty.

Nếu empty là điều kiện cần thử lại, ví dụ dữ liệu có thể xuất hiện sau khi eventual consistency đồng bộ, hãy mô hình hóa bằng repeatWhenEmpty hoặc polling policy có deadline và backoff. Không dùng retryWhen vì nó không giải quyết empty.

### Timeout cho mỗi attempt và toàn operation

~~~java
// Mỗi lần subscribe upstream bị giới hạn 250 ms.
source.timeout(Duration.ofMillis(250))
    .retryWhen(retrySpec);
~~~

~~~java
// Toàn bộ operation, gồm các lần retry, bị giới hạn 1 giây.
source.retryWhen(retrySpec)
    .timeout(Duration.ofSeconds(1));
~~~

Có thể dùng cả hai: timeout per attempt và deadline tổng thể. Tính ngân sách thời gian của tất cả downstream để tránh aggregate response vượt SLA.

## 16. Fallback phải được đánh dấu và quan sát

Fallback không nên giả dạng dữ liệu thành công.

Ví dụ dễ gây hiểu sai:

~~~java
Mono<Integer> stock = inventory.find(id)
    .onErrorReturn(0);
~~~

Nếu 0 được hiểu là hết hàng, outage có thể khiến hệ thống từ chối đơn hàng như thể đã xác nhận tồn kho bằng 0.

Cách tốt hơn:

~~~java
Mono<Section<Inventory>> stock = inventory.find(id)
    .map(Section::available)
    .switchIfEmpty(Mono.just(
        Section.empty(Inventory.unknown())))
    .onErrorResume(
        this::isRecoverable,
        error -> Mono.just(
            Section.fallback(
                Inventory.unknown(),
                "inventory_unavailable")));
~~~

Ghi metrics/log cho fallback:

~~~java
.onErrorResume(
    this::isRecoverable,
    error -> {
        meterRegistry.counter(
            "aggregation.fallback",
            "service", "inventory",
            "reason", safeReason(error))
            .increment();

        return Mono.just(
            Section.fallback(
                Inventory.unknown(),
                safeReason(error)));
    })
~~~

Tag reason phải có miền giá trị nhỏ như timeout, unavailable hoặc rejected. Không dùng error.getMessage() làm tag vì message có thể chứa ID, URL hoặc dữ liệu động. Không expose exception message nội bộ ra response.

## 17. Tổng hợp song song hay tuần tự?

Nếu các downstream độc lập, Mono.zip cho phép phối hợp chúng:

~~~java
Mono.zip(
    catalog.findById(id),
    inventory.findByProductId(id),
    recommendation.findByProductId(id),
    ProductView::new);
~~~

Thời gian hoàn tất thường bị chi phối bởi nguồn chậm nhất cộng overhead, thay vì tổng thời gian của từng nguồn nếu gọi tuần tự.

Nếu nguồn B cần ID hoặc dữ liệu từ nguồn A, dùng flatMap/zipWhen:

~~~java
catalog.findById(id)
    .flatMap(product ->
        pricing.findPrice(product.sku())
            .map(price -> new ProductPrice(product, price)));
~~~

Không viết flatMap tuần tự cho các nguồn độc lập chỉ vì dễ đọc; nó làm tăng latency. Ngược lại, không dùng zip nếu nguồn thứ hai cần giá trị của nguồn thứ nhất.

Khi Mono.zip kết thúc sớm vì một nguồn error/empty, các nguồn còn lại có thể bị cancel. Downstream HTTP client hoặc database reactive cần tôn trọng cancellation và giải phóng tài nguyên. Không giả định một nguồn đã cancel thì server bên kia chắc chắn chưa thực hiện side effect.

## 18. Aggregation bằng WebClient

WebClient là HTTP client reactive của Spring WebFlux. Một gateway có thể trả Mono<T>:

~~~java
public Mono<Inventory> findInventory(String productId) {
    return webClient.get()
        .uri("/inventory/{id}", productId)
        .retrieve()
        .bodyToMono(Inventory.class);
}
~~~

Với retrieve(), status lỗi HTTP thường được chuyển thành WebClientResponseException. Nếu downstream dùng 404 để biểu diễn "không có bản ghi", hãy ánh xạ status đó thành empty một cách tường minh.

Một cách rõ ràng là exchangeToMono:

~~~java
public Mono<Inventory> findInventory(String productId) {
    return webClient.get()
        .uri("/inventory/{id}", productId)
        .exchangeToMono(response -> {
            if (response.statusCode().is2xxSuccessful()) {
                return response.bodyToMono(Inventory.class);
            }
            if (response.statusCode().value() == 404) {
                return Mono.empty();
            }
            return response.createException()
                .flatMap(Mono::error);
        });
}
~~~

Đây là cách tường minh để 404 thành empty, còn status khác thành error. Nếu body 2xx rỗng, bodyToMono cũng có thể complete empty.

Trong ResponseSpec, onStatus yêu cầu Function<ClientResponse, Mono<? extends Throwable>>. Trả Mono.empty() từ exception function có nghĩa không chuyển status đó thành error; body vẫn được xử lý theo decoder. Nếu 404 có body hoặc semantics phức tạp, exchangeToMono thường dễ diễn đạt rõ hơn.

Timeout có thể đặt tại gateway để mọi caller có cùng giới hạn, hoặc ở aggregation service để policy thay đổi theo use case. Tránh áp timeout hai lần mà không hiểu deadline tổng thể. Gateway nên chuyển lỗi HTTP/network thành loại lỗi domain có thể phân loại; aggregation quyết định fallback theo nghiệp vụ.

## 19. Ví dụ hoàn chỉnh Java 17+ Spring Boot 3.3.5

Project dưới đây xây dựng trang tổng hợp sản phẩm từ ba gateway:

- Catalog là nguồn bắt buộc. Không tìm thấy product trả 404.
- Inventory là nguồn tùy chọn. Empty trả section EMPTY; lỗi downstream có thể phục hồi trả FALLBACK.
- Recommendations là nguồn tùy chọn. Empty trả danh sách rỗng với trạng thái EMPTY; lỗi có thể phục hồi trả FALLBACK.
- Các gateway in-memory mô phỏng success, empty và error để demo không phụ thuộc service ngoài.
- Aggregation dùng Mono.zip sau khi chuẩn hóa các nguồn optional thành Section<T> luôn phát giá trị.

### Cấu trúc project

~~~text
reactive-aggregation-demo/
├── pom.xml
└── src
    ├── main/java/com/example/aggregation
    │   ├── AggregationApplication.java
    │   ├── AggregationModels.java
    │   ├── GatewayPorts.java
    │   ├── AggregationExceptions.java
    │   ├── DemoGatewayConfiguration.java
    │   ├── ProductAggregationService.java
    │   └── ProductController.java
    └── test/java/com/example/aggregation
        ├── ProductAggregationServiceTest.java
        └── ProductAggregationHttpTest.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.5</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>reactive-aggregation-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

### AggregationApplication.java

~~~java
package com.example.aggregation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class AggregationApplication {

    public static void main(String[] args) {
        SpringApplication.run(AggregationApplication.class, args);
    }
}
~~~

### AggregationModels.java

~~~java
package com.example.aggregation;

import java.util.List;

public final class AggregationModels {

    private AggregationModels() {
    }

    public enum SectionStatus {
        AVAILABLE,
        EMPTY,
        FALLBACK
    }

    public record Product(String id, String name) {
    }

    public record Inventory(int available, boolean known) {

        public static Inventory unknown() {
            return new Inventory(0, false);
        }
    }

    public record Recommendation(String id, String title) {
    }

    public record Section<T>(
            SectionStatus status,
            T value,
            String reason) {

        public static <T> Section<T> available(T value) {
            return new Section<>(
                SectionStatus.AVAILABLE, value, null);
        }

        public static <T> Section<T> empty(T value) {
            return new Section<>(
                SectionStatus.EMPTY, value, null);
        }

        public static <T> Section<T> fallback(
                T value, String reason) {
            return new Section<>(
                SectionStatus.FALLBACK, value, reason);
        }
    }

    public record ProductView(
        Product product,
        Section<Inventory> inventory,
        Section<List<Recommendation>> recommendations) {
    }

    public record ApiError(String code, String message) {
    }
}
~~~

Section<T> giữ cả giá trị lẫn trạng thái nguồn. reason là mã an toàn, không chứa exception message hoặc dữ liệu nhạy cảm.

### GatewayPorts.java

~~~java
package com.example.aggregation;

import java.util.List;

import reactor.core.publisher.Mono;

public final class GatewayPorts {

    private GatewayPorts() {
    }

    public interface CatalogGateway {
        Mono<AggregationModels.Product> findById(String id);
    }

    public interface InventoryGateway {
        Mono<AggregationModels.Inventory> findByProductId(String id);
    }

    public interface RecommendationGateway {
        Mono<List<AggregationModels.Recommendation>>
            findByProductId(String id);
    }
}
~~~

Ba gateway trả publisher. Gateway không tự subscribe và không gọi block().

### AggregationExceptions.java

~~~java
package com.example.aggregation;

public final class AggregationExceptions {

    private AggregationExceptions() {
    }

    public static final class ProductNotFoundException
            extends RuntimeException {

        public ProductNotFoundException(String id) {
            super("Product not found: " + id);
        }
    }

    public static final class DownstreamUnavailableException
            extends RuntimeException {

        public DownstreamUnavailableException(String service) {
            super(service + " service unavailable");
        }
    }
}
~~~

### DemoGatewayConfiguration.java

~~~java
package com.example.aggregation;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static com.example.aggregation.AggregationModels.*;
import static com.example.aggregation.AggregationExceptions.*;
import static com.example.aggregation.GatewayPorts.*;

import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
public class DemoGatewayConfiguration {

    @Bean
    CatalogGateway catalogGateway() {
        return id -> {
            if ("missing".equals(id)) {
                return Mono.empty();
            }
            return Mono.just(
                new Product(id, "Notebook " + id));
        };
    }

    @Bean
    InventoryGateway inventoryGateway() {
        return id -> {
            if ("no-stock".equals(id)) {
                return Mono.empty();
            }
            if ("inventory-error".equals(id)) {
                return Mono.error(
                    new DownstreamUnavailableException("inventory"));
            }
            return Mono.just(new Inventory(8, true));
        };
    }

    @Bean
    RecommendationGateway recommendationGateway() {
        return id -> {
            if ("no-recommendations".equals(id)) {
                return Mono.empty();
            }
            if ("recommendation-error".equals(id)) {
                return Mono.error(
                    new DownstreamUnavailableException(
                        "recommendations"));
            }
            return Mono.just(List.of(
                new Recommendation("r-1", "Desk lamp"),
                new Recommendation("r-2", "Notebook stand")));
        };
    }
}
~~~

Gateway in-memory mô phỏng ba tình huống bằng ID để demo không cần microservice ngoài. Trong hệ thống thật, thay các bean này bằng WebClient gateway; không để logic mô phỏng trong production profile.

### ProductAggregationService.java

~~~java
package com.example.aggregation;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeoutException;

import org.springframework.stereotype.Service;

import static com.example.aggregation.AggregationModels.*;
import static com.example.aggregation.AggregationExceptions.*;
import static com.example.aggregation.GatewayPorts.*;

import reactor.core.publisher.Mono;

@Service
public class ProductAggregationService {

    private static final Duration DOWNSTREAM_TIMEOUT =
        Duration.ofMillis(300);

    private final CatalogGateway catalog;
    private final InventoryGateway inventory;
    private final RecommendationGateway recommendations;

    public ProductAggregationService(
            CatalogGateway catalog,
            InventoryGateway inventory,
            RecommendationGateway recommendations) {
        this.catalog = catalog;
        this.inventory = inventory;
        this.recommendations = recommendations;
    }

    public Mono<ProductView> getView(String id) {
        Mono<Product> requiredProduct =
            Mono.defer(() -> catalog.findById(id))
                .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(id)));

        Mono<Section<Inventory>> inventorySection =
            Mono.defer(() -> inventory.findByProductId(id))
                .timeout(DOWNSTREAM_TIMEOUT)
                .map(Section::available)
                .switchIfEmpty(Mono.fromSupplier(
                    () -> Section.empty(Inventory.unknown())))
                .onErrorResume(
                    this::isRecoverable,
                    error -> Mono.just(
                        Section.fallback(
                            Inventory.unknown(),
                            safeReason(error))));

        Mono<Section<List<Recommendation>>> recommendationSection =
            Mono.defer(() ->
                    recommendations.findByProductId(id))
                .timeout(DOWNSTREAM_TIMEOUT)
                .map(Section::available)
                .switchIfEmpty(Mono.just(
                    Section.empty(List.of())))
                .onErrorResume(
                    this::isRecoverable,
                    error -> Mono.just(
                        Section.fallback(
                            List.of(),
                            safeReason(error))));

        return Mono.zip(
            requiredProduct,
            inventorySection,
            recommendationSection,
            ProductView::new);
    }

    private boolean isRecoverable(Throwable error) {
        return error instanceof TimeoutException
            || error instanceof DownstreamUnavailableException;
    }

    private String safeReason(Throwable error) {
        if (error instanceof TimeoutException) {
            return "timeout";
        }
        return "downstream_unavailable";
    }
}
~~~

Giải thích service:

1. Product là nguồn bắt buộc. Catalog empty được chuyển thành ProductNotFoundException.
2. Inventory được gọi trong Mono.defer để lời gọi gateway chỉ diễn ra khi subscription cần nó.
3. Inventory timeout sau 300 ms. Nếu empty, section EMPTY mang Inventory.unknown().
4. Inventory timeout hoặc DownstreamUnavailableException được chuyển thành section FALLBACK.
5. Recommendations áp dụng chính sách tương tự; empty tạo danh sách rỗng với trạng thái EMPTY.
6. Lỗi không nằm trong danh sách recoverable tiếp tục propagate.
7. Khi hai nguồn optional đã được chuẩn hóa thành publisher luôn phát Section, Mono.zip có đủ giá trị để tạo ProductView nếu catalog thành công.
8. Không có exception message được đưa vào response reason.

### ProductController.java

~~~java
package com.example.aggregation;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import static com.example.aggregation.AggregationModels.*;
import static com.example.aggregation.AggregationExceptions.*;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductAggregationService service;

    public ProductController(ProductAggregationService service) {
        this.service = service;
    }

    @GetMapping("/{id}/view")
    public Mono<ProductView> view(@PathVariable String id) {
        return service.getView(id);
    }

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<ApiError> notFound(
            ProductNotFoundException error) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(new ApiError(
                "PRODUCT_NOT_FOUND",
                "Requested product does not exist"));
    }
}
~~~

Exception handler không trả exception message nội bộ ra ngoài. ProductNotFoundException được chuyển thành HTTP 404 và một error code ổn định.

## 20. Kiểm thử service bằng StepVerifier

StepVerifier kiểm tra tín hiệu của publisher và các trạng thái partial mà không cần mở HTTP server.

### ProductAggregationServiceTest.java

~~~java
package com.example.aggregation;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.List;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static com.example.aggregation.AggregationModels.*;
import static com.example.aggregation.AggregationExceptions.*;
import static com.example.aggregation.GatewayPorts.*;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ProductAggregationServiceTest {

    private CatalogGateway catalog;
    private InventoryGateway inventory;
    private RecommendationGateway recommendations;
    private ProductAggregationService service;

    @BeforeEach
    void setUp() {
        catalog = mock(CatalogGateway.class);
        inventory = mock(InventoryGateway.class);
        recommendations = mock(RecommendationGateway.class);
        service = new ProductAggregationService(
            catalog, inventory, recommendations);
    }

    @Test
    void allSourcesAvailableProducesCompleteView() {
        when(catalog.findById("p1"))
            .thenReturn(Mono.just(new Product("p1", "Notebook")));
        when(inventory.findByProductId("p1"))
            .thenReturn(Mono.just(new Inventory(5, true)));
        when(recommendations.findByProductId("p1"))
            .thenReturn(Mono.just(List.of(
                new Recommendation("r1", "Lamp"))));

        StepVerifier.create(service.getView("p1"))
            .assertNext(view -> {
                assertEquals("p1", view.product().id());
                assertEquals(
                    SectionStatus.AVAILABLE,
                    view.inventory().status());
                assertEquals(
                    5,
                    view.inventory().value().available());
                assertEquals(
                    SectionStatus.AVAILABLE,
                    view.recommendations().status());
                assertEquals(
                    1,
                    view.recommendations().value().size());
            })
            .verifyComplete();
    }

    @Test
    void emptyInventoryBecomesEmptySection() {
        when(catalog.findById("p1"))
            .thenReturn(Mono.just(new Product("p1", "Notebook")));
        when(inventory.findByProductId("p1"))
            .thenReturn(Mono.empty());
        when(recommendations.findByProductId("p1"))
            .thenReturn(Mono.just(List.of()));

        StepVerifier.create(service.getView("p1"))
            .assertNext(view -> {
                assertEquals(
                    SectionStatus.EMPTY,
                    view.inventory().status());
                assertFalse(view.inventory().value().known());
                assertEquals(
                    SectionStatus.AVAILABLE,
                    view.recommendations().status());
            })
            .verifyComplete();
    }

    @Test
    void inventoryErrorBecomesFallbackSection() {
        when(catalog.findById("p1"))
            .thenReturn(Mono.just(new Product("p1", "Notebook")));
        when(inventory.findByProductId("p1"))
            .thenReturn(Mono.error(
                new DownstreamUnavailableException("inventory")));
        when(recommendations.findByProductId("p1"))
            .thenReturn(Mono.just(List.of()));

        StepVerifier.create(service.getView("p1"))
            .assertNext(view -> {
                assertEquals(
                    SectionStatus.FALLBACK,
                    view.inventory().status());
                assertEquals(
                    "downstream_unavailable",
                    view.inventory().reason());
                assertFalse(view.inventory().value().known());
            })
            .verifyComplete();
    }

    @Test
    void recommendationErrorDoesNotFailRequiredProduct() {
        when(catalog.findById("p1"))
            .thenReturn(Mono.just(new Product("p1", "Notebook")));
        when(inventory.findByProductId("p1"))
            .thenReturn(Mono.just(new Inventory(5, true)));
        when(recommendations.findByProductId("p1"))
            .thenReturn(Mono.error(
                new DownstreamUnavailableException(
                    "recommendations")));

        StepVerifier.create(service.getView("p1"))
            .assertNext(view -> {
                assertEquals("p1", view.product().id());
                assertEquals(
                    SectionStatus.AVAILABLE,
                    view.inventory().status());
                assertEquals(
                    SectionStatus.FALLBACK,
                    view.recommendations().status());
                assertTrue(view.recommendations().value().isEmpty());
            })
            .verifyComplete();
    }

    @Test
    void missingRequiredProductFailsAggregation() {
        when(catalog.findById("missing"))
            .thenReturn(Mono.empty());
        when(inventory.findByProductId("missing"))
            .thenReturn(Mono.just(new Inventory(5, true)));
        when(recommendations.findByProductId("missing"))
            .thenReturn(Mono.just(List.of()));

        StepVerifier.create(service.getView("missing"))
            .expectError(ProductNotFoundException.class)
            .verify();
    }
}
~~~

Năm test chứng minh:

- Khi mọi nguồn có dữ liệu, aggregate trả AVAILABLE.
- Inventory empty được phân biệt với inventory lỗi.
- Inventory lỗi có thể được fallback mà không làm hỏng product.
- Recommendation lỗi không làm mất product và inventory.
- Catalog empty là lỗi domain vì nguồn này bắt buộc.

### Kiểm tra hành vi empty của zip trực tiếp

Đây là test snippet độc lập, có thể thêm vào một test class:

~~~java
@Test
void zipCompletesEmptyWhenOneSourceIsEmpty() {
    StepVerifier.create(
            Mono.zip(
                Mono.just("product"),
                Mono.<Integer>empty(),
                (name, stock) -> name + ":" + stock))
        .verifyComplete();
}
~~~

Combinator không được gọi vì thiếu giá trị stock. Nếu nghiệp vụ muốn hiển thị partial result, chuẩn hóa nguồn optional trước zip.

## 21. Kiểm thử HTTP bằng WebTestClient

Integration test kiểm tra controller, JSON serialization và exception mapping.

### ProductAggregationHttpTest.java

~~~java
package com.example.aggregation;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ProductAggregationHttpTest {

    @Autowired
    private WebTestClient client;

    @Test
    void allServicesAvailableReturnsCompleteView() {
        client.get()
            .uri("/api/products/p1/view")
            .accept(MediaType.APPLICATION_JSON)
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(
                    MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.product.id").isEqualTo("p1")
            .jsonPath("$.inventory.status")
                .isEqualTo("AVAILABLE")
            .jsonPath("$.inventory.value.available")
                .isEqualTo(8)
            .jsonPath("$.recommendations.status")
                .isEqualTo("AVAILABLE")
            .jsonPath("$.recommendations.value")
                .isArray();
    }

    @Test
    void emptyInventoryIsReportedAsEmpty() {
        client.get()
            .uri("/api/products/no-stock/view")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.inventory.status")
                .isEqualTo("EMPTY")
            .jsonPath("$.inventory.value.known")
                .isEqualTo(false);
    }

    @Test
    void inventoryFailureUsesFallbackWithoutLosingProduct() {
        client.get()
            .uri("/api/products/inventory-error/view")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.product.id")
                .isEqualTo("inventory-error")
            .jsonPath("$.inventory.status")
                .isEqualTo("FALLBACK")
            .jsonPath("$.inventory.reason")
                .isEqualTo("downstream_unavailable");
    }

    @Test
    void recommendationFailureKeepsOtherSections() {
        client.get()
            .uri("/api/products/recommendation-error/view")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.product.id")
                .isEqualTo("recommendation-error")
            .jsonPath("$.inventory.status")
                .isEqualTo("AVAILABLE")
            .jsonPath("$.recommendations.status")
                .isEqualTo("FALLBACK")
            .jsonPath("$.recommendations.value")
                .isArray();
    }

    @Test
    void noRecommendationsIsEmptyNotFallback() {
        client.get()
            .uri("/api/products/no-recommendations/view")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.recommendations.status")
                .isEqualTo("EMPTY")
            .jsonPath("$.recommendations.value")
                .isArray();
    }

    @Test
    void missingCatalogProductReturns404() {
        client.get()
            .uri("/api/products/missing/view")
            .exchange()
            .expectStatus().isNotFound()
            .expectBody()
            .jsonPath("$.code")
                .isEqualTo("PRODUCT_NOT_FOUND");
    }
}
~~~

Test HTTP kiểm tra response partial có trạng thái rõ ràng. Danh sách recommendation rỗng do service không có dữ liệu là EMPTY; danh sách rỗng do service lỗi là FALLBACK. Hai response có cùng dạng value nhưng khác meaning.

## 22. Chạy project

Yêu cầu Java 17+ và Maven 3.8+.

~~~bash
java -version
mvn -version
mvn -q clean test
~~~

Project có 5 test service và 6 test HTTP. Test zip empty trong phần trước là snippet độc lập; nếu thêm vào test class thì tổng số test tăng thêm một.

Khi 11 test của hai class pass, Maven kết thúc với exit code 0. Ví dụ summary minh họa:

~~~text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 0
Tests run: 6, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
~~~

Đây là output kỳ vọng, không phải kết quả Maven đã được chạy trong lúc soạn bài.

Khởi động ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Gọi product bình thường:

~~~bash
curl -i "http://localhost:8080/api/products/p1/view"
~~~

Response chứa product, inventory AVAILABLE và recommendations AVAILABLE.

Gọi trường hợp inventory empty:

~~~bash
curl -i "http://localhost:8080/api/products/no-stock/view"
~~~

Response vẫn HTTP 200 vì product bắt buộc tồn tại. Section inventory có status EMPTY và known=false.

Gọi trường hợp inventory lỗi:

~~~bash
curl -i "http://localhost:8080/api/products/inventory-error/view"
~~~

Response vẫn có product. Section inventory có status FALLBACK và reason downstream_unavailable.

Gọi trường hợp recommendation lỗi:

~~~bash
curl -i "http://localhost:8080/api/products/recommendation-error/view"
~~~

Response vẫn có product và inventory. Recommendations có FALLBACK cùng danh sách rỗng.

Gọi catalog không tìm thấy:

~~~bash
curl -i "http://localhost:8080/api/products/missing/view"
~~~

Status mong đợi: HTTP 404 Not Found, body có code PRODUCT_NOT_FOUND.

## 23. Các lỗi thường gặp và cách khắc phục

1. **Coi Mono.empty() như onError.** Empty là completion bình thường; dùng defaultIfEmpty/switchIfEmpty.
2. **Dùng defaultIfEmpty để xử lý timeout.** Timeout là error; dùng onErrorResume hoặc retry.
3. **Dùng onErrorResume để xử lý empty.** Empty không gọi error handler; dùng switchIfEmpty.
4. **Dùng switchIfEmpty để xử lý lỗi HTTP.** WebClient retrieve thường phát WebClientResponseException cho status lỗi; map status thành empty hoặc domain error tường minh.
5. **Fallback eager gây gọi database dù cache hit.** Dùng Mono.defer(() -> database.find(...)).
6. **Tạo publisher trước rồi đặt trong defer.** Defer chỉ trả publisher cũ; đưa việc gọi gateway vào supplier.
7. **Mono.zip với một nguồn optional có thể empty.** Chuẩn hóa empty thành Section/default/Optional trước khi zip.
8. **Cho rằng zipDelayError tự thay empty.** Nó trì hoãn lỗi, không biến empty thành giá trị.
9. **Zip Mono<Void> với Mono<T>.** Mono<Void> không phát element; dùng thenReturn, delayUntil hoặc Mono.when.
10. **Bắt mọi Throwable rồi trả dữ liệu mặc định.** Có thể che programming bug, authentication hoặc validation error; lọc recoverable exception.
11. **Retry sau fallback.** Fallback đã chuyển error thành onNext; retry không còn thấy lỗi. Retry trước fallback.
12. **Retry empty bằng retryWhen.** retryWhen xử lý onError; empty cần repeat/polling policy có giới hạn.
13. **Đặt timeout chỉ ở ngoài aggregate.** Một nguồn chậm có thể giữ toàn bộ response; đặt timeout per-service và deadline tổng thể.
14. **Không phân biệt EMPTY với FALLBACK.** Consumer hiểu sai nguyên nhân; dùng trạng thái trong response.
15. **Trả exception message ra API.** Có thể lộ URL, host hoặc dữ liệu nội bộ; dùng error code an toàn.
16. **Dùng onErrorComplete để che mọi lỗi.** Error biến mất thành empty; ghi nhận và dùng policy có trạng thái rõ.
17. **Dùng onErrorContinue như cơ chế chung.** Semantics phụ thuộc operator; xử lý lỗi ngay trên từng publisher.
18. **Gọi subscribe() trong service aggregation.** Mất error propagation và cancellation; compose publisher rồi return.
19. **Dùng flatMap tuần tự cho nguồn độc lập.** Tăng latency; dùng zip khi tất cả nguồn cần thiết độc lập.
20. **Dùng zip cho nguồn phụ thuộc giá trị nguồn khác.** Combinator chỉ chạy khi tất cả có giá trị; dùng flatMap/zipWhen.
21. **Không nghĩ tới cancellation.** Khi zip kết thúc sớm, nguồn khác có thể bị cancel; external calls phải cleanup.
22. **Không ghi nhận fallback rate.** Outage có thể bị che giấu; thêm counter theo service và reason hữu hạn.
23. **Cache dữ liệu fallback quá lâu.** Dữ liệu cũ có thể trở thành nguồn sai; định nghĩa TTL và trạng thái stale.
24. **Dùng default 0 cho inventory không rõ.** 0 có nghĩa hết hàng; dùng known flag hoặc Section status.
25. **Chỉ test happy path.** Bỏ sót empty/error; kiểm thử riêng từng nguồn và từng trạng thái.
26. **Không test downstream trả HTTP 404.** WebClient có thể biến nó thành error; kiểm tra mapping status theo hợp đồng.
27. **Không có deadline tổng thể.** Tổng thời gian retry/fallback vượt SLA; tính ngân sách thời gian và timeout outer.
28. **Fallback publisher cũng có thể lỗi.** Xác định lỗi fallback có propagate hay có fallback thứ hai; không giả định nó luôn thành công.

## 24. Checklist thiết kế aggregation

Trước khi phát hành API tổng hợp, hãy trả lời:

- Nguồn nào bắt buộc và nguồn nào optional?
- Empty của từng nguồn có ý nghĩa nghiệp vụ gì?
- Empty có nên trở thành 404, list rỗng hay một section EMPTY?
- Lỗi nào recoverable và lỗi nào phải propagate?
- Có phân biệt EMPTY với FALLBACK trong response không?
- Fallback value có thể bị hiểu sai như dữ liệu thật không?
- Có reason code an toàn và metrics cho fallback không?
- Fallback được tạo lazy bằng Mono.defer khi cần không?
- Retry có giới hạn số lần và chỉ cho lỗi transient không?
- Retry có nằm trước fallback không?
- Empty có bị retry nhầm không?
- Timeout per downstream có hợp lý không?
- Có deadline tổng thể cho aggregate không?
- Mono.zip có nhận publisher luôn phát giá trị ở tất cả optional branches không?
- Có vô tình zip Mono<Void> không?
- Nguồn độc lập có được gọi song song không?
- Nguồn phụ thuộc có dùng flatMap/zipWhen đúng không?
- Cancellation có giải phóng HTTP/database resources không?
- WebClient status mapping có phân biệt 404 với 5xx không?
- Error response có tránh lộ exception nội bộ không?
- Có test success, empty, error, timeout, not-found và fallback failure không?
- Có metrics cho downstream latency, error, empty và fallback rate không?
- Có log/trace đủ để điều tra mà không ghi secret hoặc PII không?

## 25. Bài tập tự kiểm tra

**Câu 1.** Mono.empty() kết thúc bằng tín hiệu nào?  
**Đáp án:** onComplete mà không có onNext.

**Câu 2.** defaultIfEmpty() xử lý empty hay error?  
**Đáp án:** Chỉ empty completion.

**Câu 3.** switchIfEmpty() khác defaultIfEmpty() như thế nào?  
**Đáp án:** switchIfEmpty chuyển sang Publisher khác; defaultIfEmpty phát một giá trị mặc định.

**Câu 4.** Vì sao nên dùng Mono.defer cho cache fallback?  
**Đáp án:** Để chỉ gọi/tạo fallback publisher khi cache empty, tránh eager side effect.

**Câu 5.** onErrorResume có xử lý Mono.empty() không?  
**Đáp án:** Không; nó chỉ xử lý onError.

**Câu 6.** doOnError có thay thế error bằng fallback không?  
**Đáp án:** Không; nó chỉ thực hiện side effect quan sát lỗi.

**Câu 7.** Mono.zip có phát tuple nếu một nguồn empty không?  
**Đáp án:** Không; kết quả complete empty và combinator không được gọi.

**Câu 8.** zipDelayError có biến empty thành giá trị không?  
**Đáp án:** Không; nó trì hoãn lỗi, nhưng empty vẫn làm kết quả empty.

**Câu 9.** Vì sao Mono<Void> không dùng làm một thành phần zip?  
**Đáp án:** Mono<Void> không phát element để combinator nhận.

**Câu 10.** Làm sao giữ giá trị sau một side effect Mono<Void>?  
**Đáp án:** Dùng flatMap rồi thenReturn(value), hoặc delayUntil khi phù hợp.

**Câu 11.** Retry nên đặt trước hay sau fallback?  
**Đáp án:** Thường đặt trước fallback để retry còn nhìn thấy error.

**Câu 12.** retryWhen có retry khi source empty không?  
**Đáp án:** Không; nó xử lý error. Empty cần repeat/polling policy riêng.

**Câu 13.** Vì sao partial result nên có status?  
**Đáp án:** Để consumer phân biệt dữ liệu thật, không có dữ liệu và dữ liệu fallback.

**Câu 14.** Nguồn catalog bắt buộc empty nên xử lý thế nào?  
**Đáp án:** Chuyển thành domain error như ProductNotFoundException và ánh xạ HTTP 404.

**Câu 15.** Khi nào dùng Mono.zip thay flatMap?  
**Đáp án:** Khi các nguồn độc lập và tất cả đều cần có giá trị để tạo kết quả.

**Câu 16.** WebClient retrieve() có tự coi 404 là Mono.empty không?  
**Đáp án:** Không mặc định; status lỗi thường thành WebClientResponseException. Phải map 404 tường minh.

**Câu 17.** Fallback error có nên được log/đo không?  
**Đáp án:** Có, bằng log/metrics với reason hữu hạn và không chứa dữ liệu nhạy cảm.

**Câu 18.** Nếu fallback cũng lỗi thì sao?  
**Đáp án:** Error đó propagate trừ khi có policy phục hồi tiếp theo; cần quyết định rõ.

## 26. Ghi nhớ

Reactor phân biệt value, empty completion và error. defaultIfEmpty/switchIfEmpty xử lý empty; onErrorReturn/onErrorResume xử lý error; doOnError chỉ quan sát; onErrorMap đổi loại lỗi. Mono.defer giúp chỉ tạo fallback khi cần.

Mono.zip yêu cầu mỗi nguồn phát một giá trị. Nếu một nguồn empty, kết quả zip cũng empty; nếu một nguồn error, zip có thể kết thúc sớm và cancel nguồn khác. zipDelayError trì hoãn lỗi nhưng không biến empty thành value. Với aggregation, chuẩn hóa các nguồn optional thành Section<T> có trạng thái AVAILABLE, EMPTY hoặc FALLBACK trước khi zip. Nguồn bắt buộc có thể chuyển empty thành domain error như 404.

Đặt timeout và retry có giới hạn trước fallback; retry chỉ xử lý error, không xử lý empty. Chỉ fallback cho lỗi recoverable, giữ reason code an toàn, ghi metrics/log và không để dữ liệu dự phòng giả dạng dữ liệu thật. Dùng zip cho nguồn độc lập, flatMap/zipWhen cho nguồn phụ thuộc, và Mono.when cho side effect Mono<Void>. Kiểm thử riêng success, empty, error, timeout, cancellation và partial response.

### Tài liệu tham khảo

- Project Reactor 3.6, [Reference Guide — Error Handling](https://projectreactor.io/docs/core/3.6.11/reference/index.html#which.errors).
- Project Reactor 3.6, [Reference Guide — Empty Mono with zip/zipWhen](https://projectreactor.io/docs/core/3.6.11/reference/index.html#faq.zipWhen).
- Project Reactor 3.6, [Mono Javadoc](https://projectreactor.io/docs/core/3.6.11/api/reactor/core/publisher/Mono.html).
- Project Reactor 3.6, [Flux Javadoc](https://projectreactor.io/docs/core/3.6.11/api/reactor/core/publisher/Flux.html).
- Spring Framework 6.1, [WebClient Reference](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html).
- Spring Framework 6.1, [WebClient.ResponseSpec Javadoc](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/web/reactive/function/client/WebClient.ResponseSpec.html).
- Spring Boot 3.3, [Testing Spring Boot Applications](https://docs.spring.io/spring-boot/docs/3.3.5/reference/html/features.html#features.testing).
