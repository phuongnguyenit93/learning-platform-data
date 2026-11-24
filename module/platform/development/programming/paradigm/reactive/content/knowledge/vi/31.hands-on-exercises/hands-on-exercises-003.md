# Bài thực hành

## Tổng hợp nhiều API với giới hạn đồng thời và thời gian chờ

Trong mô-đun **REACTIVE_PROGRAMMING**, ta học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams. Ta thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Bài thực hành này đưa các kỹ năng đó vào một tình huống thường gặp: một endpoint cần gọi nhiều API để dựng một kết quả tổng hợp, xử lý nhiều mã định danh trong cùng request và vẫn phải giữ số lời gọi đồng thời cùng thời gian chờ trong giới hạn đã định.

Ví dụ xuyên suốt là API dựng danh sách thông tin sản phẩm. Với mỗi mã sản phẩm, hệ thống cần lấy thông tin cơ bản từ Catalog, giá từ Pricing và số lượng tồn từ Inventory. Ba lời gọi độc lập có thể chạy đồng thời để giảm thời gian chờ. Tuy nhiên, nếu một request chứa nhiều mã sản phẩm và mỗi mã lại gọi ba dịch vụ, số lời gọi ra ngoài có thể tăng rất nhanh. Ta cần giới hạn concurrency, đặt timeout ở đúng ranh giới và quyết định rõ cách xử lý khi một nguồn lỗi.

Mục tiêu không chỉ là viết được `Mono.zip` và `flatMap`. Ta cần hiểu giới hạn concurrency đang áp dụng cho nhóm công việc nào, timeout đo một lần gọi hay toàn bộ batch, lỗi của một phần tử ảnh hưởng tới những phần tử còn lại ra sao, và cancellation được truyền tới các API đang hoạt động như thế nào.

### Mục tiêu học tập

Sau bài này, bạn có thể:

- Tổng hợp kết quả từ nhiều API độc lập bằng `Mono.zip`.
- Xử lý nhiều mã định danh với `flatMap` hoặc `flatMapSequential` có giới hạn concurrency.
- Phân biệt concurrency của từng batch với giới hạn tải toàn ứng dụng.
- Đặt timeout cho từng API, cho một mục tổng hợp và cho toàn batch.
- Kết hợp retry có giới hạn, backoff và fallback có điều kiện.
- Chọn chính sách all-or-nothing hoặc partial result theo hợp đồng nghiệp vụ.
- Hiểu cancellation khi timeout hoặc lỗi xảy ra trong một nhánh.
- Kiểm thử concurrency, timeout, thứ tự và cancellation bằng `StepVerifier`.
- Đo lường để điều chỉnh concurrency theo connection pool và năng lực dependency.

## 1. Bài toán cần giải quyết

Một endpoint nhận danh sách mã sản phẩm và trả về thông tin tổng hợp:

- Catalog API trả tên, mô tả và trạng thái hiển thị.
- Pricing API trả giá hiện tại.
- Inventory API trả lượng hàng có thể bán.
- Service tổng hợp ba kết quả thành một `ProductView`.

Nếu chỉ xử lý một sản phẩm, có thể ghép ba API độc lập bằng `Mono.zip`. Nhưng request có thể chứa nhiều sản phẩm. Nếu gọi từng sản phẩm tuần tự, độ trễ sẽ gần bằng tổng thời gian của tất cả lời gọi. Nếu gọi mọi thứ đồng thời mà không giới hạn, hệ thống có thể tạo quá nhiều request tới các dependency.

~~~mermaid
flowchart TD
    A[Danh sách product IDs] --> B[Giới hạn số sản phẩm đang xử lý]
    B --> C[Product 1]
    B --> D[Product 2]
    B --> E[Product N]
    C --> F1[Catalog]
    C --> F2[Pricing]
    C --> F3[Inventory]
    D --> G1[Catalog]
    D --> G2[Pricing]
    D --> G3[Inventory]
    E --> H1[Catalog]
    E --> H2[Pricing]
    E --> H3[Inventory]
    F1 --> I[Tổng hợp ProductView]
    F2 --> I
    F3 --> I
~~~

Với mỗi sản phẩm, ba API có thể được gọi song song. Giữa các sản phẩm, ta giới hạn số workflow đang hoạt động. Như vậy, thời gian chờ của một sản phẩm gần với API chậm nhất trong ba API, còn số workflow đồng thời được kiểm soát.

### Hợp đồng kết quả

Trong bài này, giả sử:

- Catalog và Pricing là dữ liệu bắt buộc.
- Inventory có thể dùng cache gần nhất nếu dịch vụ tạm thời không khả dụng.
- Nếu Catalog không tìm thấy sản phẩm, mục đó là lỗi nghiệp vụ.
- Nếu một mục bắt buộc thất bại, batch mặc định thất bại toàn bộ.
- Request batch có kích thước hữu hạn, ví dụ tối đa 50 mã.
- Client cần nhận kết quả theo thứ tự mã đầu vào.

Các giả định này quyết định cách dùng `zip`, fallback và toán tử giữ thứ tự. Trong hệ thống khác, hợp đồng có thể cho phép trả partial result hoặc bỏ qua sản phẩm không hợp lệ; khi đó pipeline phải thể hiện chính sách đó rõ ràng.

## 2. Khai báo kiểu dữ liệu và API client

Dùng kiểu dữ liệu riêng để biểu diễn response từ từng API:

~~~java
record Product(
    String id,
    String name,
    String description
) {}

record Price(
    BigDecimal amount,
    String currency
) {}

record Stock(
    int available
) {
    static Stock unavailable() {
        return new Stock(0);
    }
}

record ProductView(
    String id,
    String name,
    String description,
    BigDecimal price,
    String currency,
    int available
) {}
~~~

Các client trả Publisher thay vì tự subscribe:

~~~java
interface CatalogClient {
    Mono<Product> find(String productId);
}

interface PricingClient {
    Mono<Price> currentPrice(String productId);
}

interface InventoryClient {
    Mono<Stock> availableStock(String productId);
}

interface InventoryCache {
    Mono<Stock> latestKnownStock(String productId);
}
~~~

Mỗi phương thức trả `Mono` vì một mã sản phẩm tương ứng tối đa một response cho từng API. Nếu một API trả danh sách nhiều bản ghi, có thể dùng `Flux` rồi tổng hợp hoặc giới hạn dữ liệu theo hợp đồng.

Không gọi `block()` để lấy response trong service. Việc gọi API cần được ghép vào pipeline để caller có thể điều khiển timeout, lỗi, demand và cancellation.

## 3. Tổng hợp ba API bằng Mono.zip

Catalog, Pricing và Inventory độc lập sau khi đã có product ID. Ta có thể đăng ký cả ba nguồn và kết hợp kết quả bằng `Mono.zip`:

~~~java
Mono<ProductView> loadOne(String productId) {
    return Mono.zip(
        catalogClient.find(productId),
        pricingClient.currentPrice(productId),
        inventoryClient.availableStock(productId)
    )
    .map(tuple -> {
        Product product = tuple.getT1();
        Price price = tuple.getT2();
        Stock stock = tuple.getT3();

        return new ProductView(
            product.id(),
            product.name(),
            product.description(),
            price.amount(),
            price.currency(),
            stock.available()
        );
    });
}
~~~

Khi subscribe, các Publisher đầu vào của `zip` được đăng ký. Mỗi nguồn phát một giá trị; khi cả ba giá trị đã có, mapper tạo `ProductView`.

Nếu một nguồn phát lỗi, `zip` phát lỗi tới downstream và hủy các nguồn còn lại mà nó quản lý. Nếu một nguồn hoàn tất rỗng trước khi phát giá trị, `zip` có thể hoàn tất rỗng vì không thể tạo tuple đầy đủ.

### Xử lý nguồn rỗng

Cần xác định response rỗng có nghĩa gì:

- Catalog rỗng thường có nghĩa sản phẩm không tồn tại; nên chuyển thành lỗi nghiệp vụ.
- Pricing rỗng có thể là lỗi dữ liệu nếu mọi sản phẩm phải có giá.
- Inventory rỗng có thể được hiểu là chưa có thông tin tồn kho và dùng giá trị mặc định nếu nghiệp vụ cho phép.

Ví dụ:

~~~java
Mono<Product> product =
    catalogClient.find(productId)
        .switchIfEmpty(Mono.error(
            new ProductNotFoundException(productId)
        ));

Mono<Price> price =
    pricingClient.currentPrice(productId)
        .switchIfEmpty(Mono.error(
            new PriceUnavailableException(productId)
        ));

Mono<Stock> stock =
    inventoryClient.availableStock(productId)
        .defaultIfEmpty(Stock.unavailable());
~~~

Sau đó ghép ba Mono:

~~~java
return Mono.zip(product, price, stock)
    .map(tuple -> toView(tuple.getT1(), tuple.getT2(), tuple.getT3()));
~~~

Không dùng `defaultIfEmpty` một cách tùy tiện. Giá trị mặc định chỉ hợp lệ khi nó có ý nghĩa nghiệp vụ. Gán giá bằng 0 cho một lỗi Pricing có thể khiến hệ thống hiển thị một mức giá sai.

## 4. Đặt timeout cho từng API

Một dependency chậm có thể giữ cả workflow chờ. Đặt timeout riêng cho từng lời gọi để giới hạn thời gian chờ và giúp xác định nguồn gây chậm:

~~~java
private static final Duration API_TIMEOUT =
    Duration.ofMillis(250);

Mono<Product> product =
    catalogClient.find(productId)
        .timeout(API_TIMEOUT);

Mono<Price> price =
    pricingClient.currentPrice(productId)
        .timeout(API_TIMEOUT);

Mono<Stock> stock =
    inventoryClient.availableStock(productId)
        .timeout(API_TIMEOUT);
~~~

Vì ba lời gọi chạy đồng thời trong `zip`, thời gian tổng hợp không phải tổng ba timeout. Nếu mỗi API hoàn tất trong 100 ms, bước tổng hợp thường có thể hoàn tất gần 100 ms cộng overhead. Nếu một API chờ quá 250 ms, nhánh đó timeout và cả kết quả tổng hợp thất bại, trừ khi có fallback.

Timeout ở đây giới hạn thời gian chờ của từng Publisher. Nó không bảo đảm server từ xa đã dừng xử lý. Client reactive có thể hủy request hoặc ngừng tiêu thụ response; dịch vụ đích có thể đã nhận request và vẫn tiếp tục công việc.

### Dùng helper để áp dụng chính sách đồng nhất

Có thể đóng gói timeout trong helper:

~~~java
private <T> Mono<T> withApiTimeout(
    Supplier<Mono<T>> request
) {
    return Mono.defer(request)
        .timeout(API_TIMEOUT);
}
~~~

`Mono.defer` gọi supplier khi có subscription. Điều này bảo đảm mỗi lần subscribe hoặc retry tạo Publisher theo thời điểm thực thi, thay vì gọi hàm client ngay khi lắp ráp pipeline.

Sử dụng:

~~~java
Mono<Product> product =
    withApiTimeout(() -> catalogClient.find(productId));

Mono<Price> price =
    withApiTimeout(() -> pricingClient.currentPrice(productId));

Mono<Stock> stock =
    withApiTimeout(() -> inventoryClient.availableStock(productId));
~~~

Nếu client đã trả một Publisher lazy, việc bọc bằng `defer` vẫn hữu ích khi muốn helper kiểm soát thời điểm gọi method và tạo lại Publisher khi retry.

## 5. Retry có giới hạn cho lỗi tạm thời

Một số lỗi có thể tạm thời: connection reset, gateway trả 503 hoặc timeout thoáng qua. Có thể retry với backoff và giới hạn số lần:

~~~java
private <T> Mono<T> callWithRetry(
    Supplier<Mono<T>> request
) {
    return Mono.defer(request)
        .timeout(API_TIMEOUT)
        .retryWhen(
            Retry.backoff(1, Duration.ofMillis(50))
                .maxBackoff(Duration.ofMillis(100))
                .jitter(0.5)
                .filter(this::isTransientFailure)
        );
}
~~~

Trong ví dụ, một API có tối đa một lần retry sau lần thử đầu. `timeout` nằm trước `retryWhen`, nên mỗi lần thử có timeout riêng. Tổng thời gian có thể gồm thời gian của lần thử đầu, backoff và lần thử lại.

Hàm phân loại lỗi phải dựa trên hợp đồng dependency:

~~~java
private boolean isTransientFailure(Throwable error) {
    return error instanceof TimeoutException
        || error instanceof WebClientRequestException
        || error instanceof ServiceUnavailableException;
}
~~~

Không retry các lỗi thường không thể khắc phục bằng cách gọi lại cùng request, ví dụ:

- Sản phẩm không tồn tại.
- Request sai định dạng.
- Không có quyền truy cập.
- Quy tắc nghiệp vụ từ chối thao tác.
- Giá trị đầu vào vi phạm validation.

Retry thao tác đọc thường dễ kiểm soát hơn thao tác ghi. Với API ghi, timeout có thể xảy ra sau khi server đã commit. Trước khi retry, cần idempotency key hoặc cơ chế truy vấn trạng thái để tránh tạo tác dụng phụ trùng.

### Timeout cho mỗi lần thử và timeout tổng khác nhau

Hai cách đặt timeout có ý nghĩa khác nhau:

~~~java
// Timeout từng lần thử; retry có thể kéo dài tổng thời gian.
Mono<Response> perAttempt =
    Mono.defer(this::callRemote)
        .timeout(API_TIMEOUT)
        .retryWhen(retryPolicy);
~~~

~~~java
// Timeout bao trọn cả lần thử và khoảng backoff.
Mono<Response> totalBudget =
    Mono.defer(this::callRemote)
        .retryWhen(retryPolicy)
        .timeout(Duration.ofMillis(700));
~~~

Có thể kết hợp cả hai: timeout ngắn cho từng lần thử và timeout ngoài cùng cho tổng ngân sách. Nếu tổng deadline hết trước khi retry hoàn tất, timeout ngoài cùng hủy chuỗi đang hoạt động.

## 6. Ghép API với retry, timeout và fallback

Ta có thể áp dụng chính sách theo từng dependency. Trong ví dụ này, Catalog và Pricing là bắt buộc; Inventory có cache fallback nếu gặp lỗi hạ tầng tạm thời:

~~~java
private Mono<Product> loadProduct(String id) {
    return callWithRetry(() -> catalogClient.find(id)
        .switchIfEmpty(Mono.error(new ProductNotFoundException(id))));
}

private Mono<Price> loadPrice(String id) {
    return callWithRetry(() -> pricingClient.currentPrice(id)
        .switchIfEmpty(Mono.error(new PriceUnavailableException(id))));
}

private Mono<Stock> loadStock(String id) {
    return callWithRetry(() -> inventoryClient.availableStock(id))
        .onErrorResume(
            this::isInventoryFallbackEligible,
            error -> inventoryCache.latestKnownStock(id)
                .switchIfEmpty(Mono.error(error))
        )
        .defaultIfEmpty(Stock.unavailable());
}
~~~

`isInventoryFallbackEligible` chỉ nên chấp nhận lỗi mà cache có thể thay thế an toàn, chẳng hạn timeout hoặc service unavailable. Không dùng cache để che giấu lỗi dữ liệu hoặc lỗi nghiệp vụ.

Hàm tổng hợp:

~~~java
private Mono<ProductView> loadOne(String id) {
    return Mono.zip(
        loadProduct(id),
        loadPrice(id),
        loadStock(id)
    )
    .map(tuple -> toView(
        tuple.getT1(),
        tuple.getT2(),
        tuple.getT3()
    ))
    .timeout(ITEM_TIMEOUT)
    .onErrorMap(error ->
        new ProductAggregationException(id, error)
    );
}
~~~

Timeout `ITEM_TIMEOUT` bao trùm cả ba nhánh. Nó bảo vệ workflow một sản phẩm ngay cả khi các timeout và retry riêng lẻ cộng lại quá lâu. Khi timeout ngoài cùng xảy ra, các subscription nhánh còn hoạt động nhận cancellation.

Không nên dùng một fallback chung cho toàn bộ `zip` nếu mỗi API có ngữ nghĩa khác nhau. Fallback cho Inventory có thể hợp lệ, trong khi fallback cho Catalog hoặc Pricing có thể tạo dữ liệu sai.

## 7. Xử lý nhiều mã sản phẩm với concurrency hữu hạn

Sau khi có `loadOne(id)`, ta cần xử lý một danh sách mã. `flatMap` cho phép nhiều Publisher con chạy đồng thời và nhận tham số giới hạn concurrency:

~~~java
Flux<ProductView> views =
    Flux.fromIterable(productIds)
        .flatMap(this::loadOne, 6);
~~~

Tham số 6 giới hạn số Publisher con của `loadOne` đang hoạt động đồng thời trong subscription này. Khi một sản phẩm hoàn tất, `flatMap` có thể subscribe sản phẩm tiếp theo.

Nếu mỗi `loadOne` gọi ba API cùng lúc, concurrency 6 có thể tạo tối đa khoảng 18 lời gọi API đang hoạt động cho một batch, giả sử mỗi nhánh vẫn đang chạy. Đây là điểm thường bị bỏ sót: concurrency của `flatMap` đang giới hạn workflow theo sản phẩm, không phải tổng số HTTP request tới tất cả dependency.

### Chọn concurrency theo fan-out

Nếu mỗi phần tử gọi ba API song song:

| Số workflow sản phẩm đồng thời | Fan-out mỗi sản phẩm | Số API call đồng thời tối đa ước tính |
|---:|---:|---:|
| 2 | 3 | 6 |
| 4 | 3 | 12 |
| 6 | 3 | 18 |
| 10 | 3 | 30 |

Đây là giới hạn gần đúng cho một batch subscription. Nhiều HTTP request đến ứng dụng cùng lúc sẽ nhân thêm số này. Nếu 20 client cùng gửi batch và mỗi batch có concurrency 6, tải tiềm năng có thể lên tới khoảng 360 API call đồng thời.

Do đó, giới hạn trong `flatMap` là cần thiết nhưng chưa đủ để bảo vệ toàn hệ thống. Cần phối hợp với connection pool, bulkhead, rate limiter hoặc giới hạn concurrency ở client/dependency boundary.

## 8. Giữ thứ tự đầu vào với flatMapSequential

`flatMap` phát kết quả theo thời điểm các Publisher con hoàn tất. Nếu sản phẩm thứ ba hoàn tất trước sản phẩm thứ nhất, kết quả thứ ba có thể xuất hiện trước.

Nếu API cần giữ thứ tự danh sách đầu vào nhưng vẫn muốn xử lý đồng thời, dùng `flatMapSequential`:

~~~java
Flux<ProductView> views =
    Flux.fromIterable(productIds)
        .flatMapSequential(this::loadOne, 6);
~~~

Các inner Publisher vẫn được subscribe đồng thời trong giới hạn 6, nhưng kết quả được phát theo thứ tự nguồn. Nếu phần tử đầu tiên chậm, kết quả của các phần tử sau đã hoàn tất có thể phải chờ trong buffer.

Nếu thứ tự không quan trọng, `flatMap` thường cho phép kết quả hoàn tất sớm được phát ngay. Nếu cần xử lý tuần tự và không muốn nhiều inner hoạt động đồng thời, dùng `concatMap`:

~~~java
Flux<ProductView> views =
    Flux.fromIterable(productIds)
        .concatMap(this::loadOne);
~~~

Chọn toán tử theo hợp đồng đầu ra:

| Toán tử | Inner hoạt động | Thứ tự kết quả |
|---|---|---|
| `flatMap(mapper, concurrency)` | Đồng thời, giới hạn theo concurrency | Theo thời điểm inner phát |
| `flatMapSequential(mapper, concurrency)` | Đồng thời, giới hạn theo concurrency | Theo thứ tự nguồn |
| `concatMap(mapper)` | Tuần tự | Theo thứ tự nguồn |

Không dùng `parallel()` chỉ vì cần gọi nhiều API. I/O non-blocking của WebClient không cần một thread CPU riêng cho mỗi request. Giới hạn concurrency ở toán tử và client pool thường là cách phù hợp hơn.

## 9. Đặt deadline cho toàn batch

Timeout từng API và từng sản phẩm vẫn chưa giới hạn tổng thời gian của một batch. Nếu request chứa nhiều sản phẩm, các nhóm có thể được xử lý nối tiếp theo từng đợt concurrency. Ta có thể đặt một deadline tổng cho batch hữu hạn:

~~~java
Mono<List<ProductView>> loadBatch(List<String> productIds) {
    if (productIds.size() > MAX_BATCH_SIZE) {
        return Mono.error(
            new BatchTooLargeException(MAX_BATCH_SIZE)
        );
    }

    return Flux.fromIterable(productIds)
        .flatMapSequential(this::loadOne, MAX_IN_FLIGHT)
        .collectList()
        .timeout(BATCH_TIMEOUT);
}
~~~

`collectList()` tạo một `Mono<List<ProductView>>` chỉ hoàn tất khi tất cả sản phẩm đã được xử lý. Timeout đặt sau `collectList` giới hạn thời gian tổng từ subscription tới khi toàn bộ batch hoàn tất. Nếu deadline hết, subscription upstream bị hủy và các workflow đang hoạt động nhận cancellation.

Giới hạn `MAX_BATCH_SIZE` quan trọng vì `collectList` giữ toàn bộ kết quả trong bộ nhớ. Không dùng mẫu này cho nguồn vô hạn hoặc batch không có giới hạn.

### Timeout trên Flux khác timeout toàn batch

Một điểm cần nhớ: `Flux.timeout(Duration)` thường áp dụng thời gian chờ cho tín hiệu đầu tiên và khoảng cách giữa các tín hiệu tiếp theo. Khi một phần tử được phát, bộ đếm thời gian chờ tín hiệu kế tiếp được thiết lập lại. Nó phù hợp với idle timeout hoặc giới hạn khoảng im lặng giữa các phần tử.

Nó không mặc nhiên có nghĩa "toàn bộ Flux phải hoàn tất trong thời lượng này". Với batch hữu hạn cần deadline tổng, chuyển sang `Mono` bằng `collectList()` hoặc dùng một Publisher bao trọn workflow rồi đặt timeout ở ngoài cùng.

Với stream dài hạn như SSE, không nên `collectList()`. Hãy chọn idle timeout, timeout cho từng thao tác con hoặc deadline theo phiên tùy hợp đồng của stream.

## 10. All-or-nothing hay partial result?

Khi một sản phẩm lỗi, cần quyết định cả batch sẽ thất bại hay vẫn trả những sản phẩm khác.

### All-or-nothing

Pipeline đơn giản:

~~~java
Mono<List<ProductView>> result =
    Flux.fromIterable(productIds)
        .flatMapSequential(this::loadOne, 6)
        .collectList()
        .timeout(BATCH_TIMEOUT);
~~~

Nếu một `loadOne` phát lỗi, lỗi truyền ra ngoài; các inner còn lại do `flatMapSequential` quản lý có thể bị hủy. Hợp đồng này phù hợp khi client cần một danh sách nhất quán và không thể chấp nhận kết quả thiếu.

### Partial result

Nếu từng sản phẩm độc lập và client chấp nhận biết sản phẩm nào thất bại, có thể chuyển lỗi của từng mục thành một kiểu kết quả:

~~~java
sealed interface BatchItem {
    record Success(ProductView value) implements BatchItem {}
    record Failure(String productId, String code) implements BatchItem {}
}
~~~

~~~java
Flux<BatchItem> result =
    Flux.fromIterable(productIds)
        .flatMapSequential(id ->
            loadOne(id)
                .map(view -> (BatchItem) new BatchItem.Success(view))
                .onErrorResume(error ->
                    Mono.just(new BatchItem.Failure(
                        id,
                        classify(error)
                    ))
                ),
            6
        );
~~~

Lỗi của một sản phẩm được biểu diễn thành `Failure`; các sản phẩm khác vẫn có thể hoàn tất. Nhưng không nên chuyển mọi lỗi thành partial result. Lỗi deadline toàn batch, lỗi xác thực request hoặc lỗi hệ thống không thể phục hồi có thể vẫn cần làm toàn request thất bại.

Nếu cần giữ deadline toàn batch trong mô hình partial result, đặt timeout ngoài cùng sau khi thu thập hoặc theo hợp đồng stream. Đừng bắt `TimeoutException` tổng rồi biến nó thành một failure cho từng phần tử nếu điều đó khiến client tưởng batch đã hoàn tất đầy đủ.

## 11. Cancellation khi timeout hoặc một nhánh lỗi

Một ưu điểm của composition là cancellation được truyền qua các Publisher được ghép.

Trong workflow một sản phẩm:

- Nếu Catalog timeout, `zip` phát lỗi.
- Các nhánh Pricing và Inventory còn hoạt động nhận cancellation.
- Nếu timeout tổng của `loadOne` xảy ra, cả ba nhánh nhận cancellation.
- Nếu batch timeout, các `loadOne` đang hoạt động nhận cancellation từ `flatMapSequential`.
- Nếu client hủy request HTTP, WebFlux hủy subscription response và cancellation truyền ngược qua batch.

Cancellation là yêu cầu dừng, không phải rollback. Một dịch vụ từ xa có thể đã nhận request và vẫn tiếp tục xử lý. Với thao tác đọc, việc ngừng tiêu thụ thường ít rủi ro; với thao tác ghi, cần idempotency và đối soát.

Có thể quan sát cancellation ở ranh giới dependency:

~~~java
Mono<Stock> stock =
    inventoryClient.availableStock(productId)
        .doOnCancel(() ->
            log.debug("Inventory lookup cancelled for {}", productId)
        );
~~~

Không nên ghi mọi cancellation thành lỗi. Nó có thể xảy ra bình thường khi một nhánh khác lỗi hoặc caller không còn cần kết quả.

## 12. Tránh nhân concurrency ngoài dự kiến

Giả sử một request xử lý 50 sản phẩm với concurrency 6 và mỗi sản phẩm gọi ba API. Một request có thể tạo tới khoảng 18 API call đang hoạt động. Nếu nhiều request đồng thời, tổng tải có thể vượt năng lực dependency dù từng batch đã giới hạn concurrency.

Các lớp kiểm soát nên phối hợp:

1. **Giới hạn kích thước batch:** từ chối request có quá nhiều ID.
2. **Concurrency theo batch:** giới hạn số workflow sản phẩm đang hoạt động.
3. **Bulkhead theo dependency:** giới hạn số lời gọi tới Catalog, Pricing và Inventory.
4. **Connection pool:** giới hạn số kết nối thực sự được mở.
5. **Rate limit:** giới hạn tốc độ gọi theo quota của dịch vụ.
6. **Timeout và cancellation:** giải phóng công việc không còn hữu ích.
7. **Queue hữu hạn:** tránh giữ vô hạn các request chờ.

Một concurrency limit trong `flatMap` chỉ có hiệu lực cho subscription đó. Nó không phải semaphore toàn ứng dụng. Để bảo vệ một dependency dùng chung bởi nhiều endpoint, cần giới hạn ở tầng client hoặc một bulkhead được chia sẻ.

Không nên tự tạo một scheduler mới cho mỗi request để "giới hạn thread". Scheduler quản lý thread thực thi, còn connection pool, concurrency và quota quản lý năng lực gọi dependency. Hai loại giới hạn giải quyết vấn đề khác nhau.

## 13. Một service hoàn chỉnh

Ví dụ sau kết hợp các phần chính. Các hằng số là giá trị minh họa; cần hiệu chỉnh bằng load test và giới hạn thực tế của dịch vụ:

~~~java
@Service
class ProductAggregationService {
    private static final Duration API_TIMEOUT =
        Duration.ofMillis(250);

    private static final Duration ITEM_TIMEOUT =
        Duration.ofMillis(650);

    private static final Duration BATCH_TIMEOUT =
        Duration.ofSeconds(3);

    private static final int MAX_IN_FLIGHT = 6;
    private static final int MAX_BATCH_SIZE = 50;

    private final CatalogClient catalogClient;
    private final PricingClient pricingClient;
    private final InventoryClient inventoryClient;
    private final InventoryCache inventoryCache;

    ProductAggregationService(
        CatalogClient catalogClient,
        PricingClient pricingClient,
        InventoryClient inventoryClient,
        InventoryCache inventoryCache
    ) {
        this.catalogClient = catalogClient;
        this.pricingClient = pricingClient;
        this.inventoryClient = inventoryClient;
        this.inventoryCache = inventoryCache;
    }

    Mono<List<ProductView>> loadBatch(List<String> ids) {
        return Mono.defer(() -> {
            if (ids.size() > MAX_BATCH_SIZE) {
                return Mono.error(
                    new BatchTooLargeException(MAX_BATCH_SIZE)
                );
            }

            return Flux.fromIterable(ids)
                .flatMapSequential(this::loadOne, MAX_IN_FLIGHT)
                .collectList()
                .timeout(BATCH_TIMEOUT);
        });
    }

    private Mono<ProductView> loadOne(String id) {
        Mono<Product> product =
            callWithPolicy(() -> catalogClient.find(id)
                .switchIfEmpty(Mono.error(
                    new ProductNotFoundException(id)
                )));

        Mono<Price> price =
            callWithPolicy(() -> pricingClient.currentPrice(id)
                .switchIfEmpty(Mono.error(
                    new PriceUnavailableException(id)
                )));

        Mono<Stock> stock =
            callWithPolicy(() -> inventoryClient.availableStock(id))
                .onErrorResume(
                    this::isInventoryFallbackEligible,
                    error -> inventoryCache.latestKnownStock(id)
                        .switchIfEmpty(Mono.error(error))
                )
                .defaultIfEmpty(Stock.unavailable());

        return Mono.zip(product, price, stock)
            .map(tuple -> toView(
                tuple.getT1(),
                tuple.getT2(),
                tuple.getT3()
            ))
            .timeout(ITEM_TIMEOUT)
            .onErrorMap(error ->
                new ProductAggregationException(id, error)
            );
    }

    private <T> Mono<T> callWithPolicy(
        Supplier<Mono<T>> request
    ) {
        return Mono.defer(request)
            .timeout(API_TIMEOUT)
            .retryWhen(
                Retry.backoff(1, Duration.ofMillis(50))
                    .maxBackoff(Duration.ofMillis(100))
                    .jitter(0.5)
                    .filter(this::isTransientFailure)
            );
    }

    private boolean isTransientFailure(Throwable error) {
        return error instanceof TimeoutException
            || error instanceof WebClientRequestException
            || error instanceof ServiceUnavailableException;
    }

    private boolean isInventoryFallbackEligible(Throwable error) {
        return error instanceof TimeoutException
            || error instanceof WebClientRequestException
            || error instanceof ServiceUnavailableException;
    }

    private ProductView toView(
        Product product,
        Price price,
        Stock stock
    ) {
        return new ProductView(
            product.id(),
            product.name(),
            product.description(),
            price.amount(),
            price.currency(),
            stock.available()
        );
    }
}
~~~

Điểm chính trong thiết kế:

- Mỗi API call có timeout và retry policy riêng.
- Inventory có fallback có điều kiện vì nghiệp vụ cho phép dùng cache.
- `Mono.zip` tổng hợp ba nguồn độc lập của một sản phẩm.
- `ITEM_TIMEOUT` giới hạn thời gian của một sản phẩm.
- `flatMapSequential` giới hạn sáu sản phẩm đồng thời và giữ thứ tự đầu vào.
- `collectList().timeout(BATCH_TIMEOUT)` đặt deadline tổng cho batch hữu hạn.
- `Mono.defer` trì hoãn validation và lắp ráp workflow tới subscription.

Trong mã thực tế, cần bổ sung xử lý lỗi cho cache, validation null/duplicate ID, metric theo dependency, trace context và kiểm tra kích thước request trước khi gọi service.

## 14. Kiểm thử timeout bằng thời gian ảo

Không cần chờ thật trong test timeout. `StepVerifier.withVirtualTime` cho phép tiến đồng hồ ảo:

~~~java
@Test
void timesOutSlowDependency() {
    StepVerifier.withVirtualTime(() ->
            Mono.<String>never()
                .timeout(Duration.ofMillis(200))
        )
        .expectSubscription()
        .thenAwait(Duration.ofMillis(200))
        .expectError(TimeoutException.class)
        .verify();
}
~~~

Publisher được tạo bên trong supplier để Reactor Test cài scheduler ảo trước khi pipeline được lắp ráp. Test xác minh timeout tạo lỗi sau 200 ms thời gian ảo.

Kiểm thử fallback:

~~~java
@Test
void usesFallbackWhenPrimaryTimesOut() {
    StepVerifier.withVirtualTime(() ->
            Mono.<String>never()
                .timeout(Duration.ofSeconds(1))
                .onErrorResume(
                    TimeoutException.class,
                    error -> Mono.just("cached")
                )
        )
        .thenAwait(Duration.ofSeconds(1))
        .expectNext("cached")
        .verifyComplete();
}
~~~

Chỉ fallback cho loại lỗi được cho phép. Một test khác nên xác minh lỗi validation hoặc lỗi nghiệp vụ không kích hoạt fallback.

## 15. Kiểm thử giới hạn concurrency

Dùng bộ đếm để quan sát số Publisher con đang hoạt động:

~~~java
@Test
void doesNotExceedConfiguredConcurrency() {
    AtomicInteger active = new AtomicInteger();
    AtomicInteger maximum = new AtomicInteger();

    StepVerifier.withVirtualTime(() ->
            Flux.range(1, 10)
                .flatMap(id ->
                    Mono.delay(Duration.ofSeconds(1))
                        .map(ignored -> id)
                        .doOnSubscribe(subscription -> {
                            int current = active.incrementAndGet();
                            maximum.accumulateAndGet(current, Math::max);
                        })
                        .doFinally(signal -> active.decrementAndGet()),
                    3
                )
        )
        .thenAwait(Duration.ofSeconds(4))
        .expectNextCount(10)
        .verifyComplete();

    assertThat(maximum.get()).isEqualTo(3);
    assertThat(active.get()).isZero();
}
~~~

Test tạo 10 Publisher con, mỗi inner chờ một giây. Concurrency được đặt là 3. Khi một inner hoàn tất, `flatMap` mới subscribe phần tử tiếp theo. Sau bốn giây ảo, tất cả 10 phần tử đã hoàn tất; giá trị active lớn nhất không vượt quá 3 và bộ đếm cuối cùng trở về 0.

Đây là kiểm thử concurrency của các inner Publisher trong một subscription. Nó không chứng minh tổng số HTTP call toàn ứng dụng bị giới hạn ở 3, cũng không tính fan-out nhiều API bên trong mỗi inner.

## 16. Kiểm thử giữ thứ tự

Với `flatMapSequential`, inner có thể hoàn tất khác thứ tự nhưng kết quả được phát theo thứ tự nguồn:

~~~java
@Test
void flatMapSequentialPreservesInputOrder() {
    StepVerifier.withVirtualTime(() ->
            Flux.range(1, 3)
                .flatMapSequential(
                    id -> Mono.delay(
                            Duration.ofMillis((4 - id) * 100L)
                        )
                        .thenReturn(id),
                    3
                )
        )
        .thenAwait(Duration.ofMillis(300))
        .expectNext(1, 2, 3)
        .verifyComplete();
}
~~~

Inner thứ ba được thiết kế hoàn tất sớm hơn inner thứ nhất, nhưng verifier vẫn nhận 1, 2, 3. Nếu đổi sang `flatMap`, thứ tự có thể theo thời điểm hoàn tất và test không nên giả định luôn là 1, 2, 3.

## 17. Kiểm thử cancellation khi batch timeout

Khi deadline tổng hết, các inner đang hoạt động cần nhận cancellation:

~~~java
@Test
void batchTimeoutCancelsActiveCalls() {
    AtomicInteger cancelled = new AtomicInteger();

    StepVerifier.withVirtualTime(() ->
            Flux.range(1, 5)
                .flatMap(id ->
                    Mono.<Integer>never()
                        .doOnCancel(cancelled::incrementAndGet),
                    2
                )
                .collectList()
                .timeout(Duration.ofSeconds(1))
        )
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(1))
        .expectError(TimeoutException.class)
        .verify();

    assertThat(cancelled.get()).isEqualTo(2);
}
~~~

Hai inner đang hoạt động do concurrency bằng 2. Khi timeout tổng xảy ra, chúng nhận cancellation. Các phần tử còn lại chưa được xử lý không tạo inner mới sau khi upstream bị hủy.

Trong ứng dụng thật, adapter HTTP hoặc database có thể không dừng tác vụ từ xa ngay lập tức. Test unit xác minh tín hiệu cancellation ở Publisher; kiểm thử tích hợp cần xác minh client connector và dependency phản ứng đúng với việc hủy.

## 18. Kiểm thử chính sách all-or-nothing và partial result

Với all-or-nothing, một inner lỗi làm batch thất bại:

~~~java
Flux<Integer> allOrNothing =
    Flux.just(1, 2, 3)
        .flatMap(id ->
            id == 2
                ? Mono.error(new IllegalStateException("failed"))
                : Mono.just(id),
            3
        );

StepVerifier.create(allOrNothing)
    .expectError(IllegalStateException.class)
    .verify();
~~~

Với partial result, lỗi từng mục được chuyển thành một giá trị failure:

~~~java
Flux<BatchItem> partial =
    Flux.just("p-1", "p-2", "p-3")
        .flatMap(id ->
            loadOne(id)
                .map(view -> (BatchItem) new BatchItem.Success(view))
                .onErrorResume(error ->
                    Mono.just(new BatchItem.Failure(
                        id,
                        classify(error)
                    ))
                ),
            3
        );
~~~

Test nên xác minh cả success và failure record, đồng thời bảo đảm timeout tổng hoặc cancellation từ caller vẫn có thể kết thúc batch theo hợp đồng.

## 19. Đo lường và điều chỉnh concurrency

Không chọn concurrency chỉ dựa vào một ví dụ hoặc số lõi CPU. Các API non-blocking vẫn bị giới hạn bởi connection pool, quota dịch vụ, thời gian phản hồi và năng lực database.

Theo dõi:

| Chỉ số | Dấu hiệu cần quan sát |
|---|---|
| p50/p95/p99 theo dependency | API nào chậm và độ trễ đuôi thay đổi ra sao |
| Số request đang hoạt động | Concurrency thực tế tới từng dịch vụ |
| Connection pool usage | Pool có cạn hoặc thời gian chờ lấy connection tăng không |
| Timeout/retry rate | Dependency có đang quá tải hoặc mất ổn định không |
| Batch latency | Tổng thời gian từ request tới kết quả cuối |
| Batch size | Request lớn có làm tăng bộ nhớ và thời gian xử lý không |
| Cancellation count | Công việc bị hủy do timeout hoặc client disconnect |
| Queue/prefetch | Có dữ liệu chờ tăng ngoài dự kiến không |

Quy trình điều chỉnh:

1. Bắt đầu với concurrency thấp và batch size giới hạn.
2. Đo latency, throughput, connection pool và tỷ lệ lỗi dưới tải đại diện.
3. Tăng concurrency từng bước.
4. Dừng tăng khi throughput không cải thiện hoặc p95/p99, timeout và queue tăng nhanh.
5. Kiểm tra tải tổng khi có nhiều request đồng thời, không chỉ một batch.
6. Đặt trần ở client/bulkhead để một endpoint không chiếm hết năng lực dependency.
7. Chạy lại kiểm thử sau mỗi thay đổi cấu hình.

Nếu CPU thấp nhưng latency cao, hãy kiểm tra I/O pool và dependency. Nếu connection pool đầy, tăng concurrency có thể làm tình hình xấu hơn. Nếu CPU bão hòa, kiểm tra các phép tính đồng bộ và tránh chạy chúng trên event loop.

## 20. Những nhầm lẫn thường gặp

- **Mono.zip làm ba API chạy song song trong mọi trường hợp:** các Publisher được subscribe trong cùng thao tác zip; nguồn blocking hoặc có side effect khi assembly vẫn có thể làm chặn thread. Dùng client non-blocking và nguồn lazy.
- **flatMap concurrency 6 nghĩa là chỉ có sáu HTTP request:** nếu mỗi inner gọi ba API, có thể có tới khoảng 18 lời gọi đang hoạt động.
- **Concurrency của một batch là giới hạn toàn ứng dụng:** mỗi subscription có giới hạn riêng; nhiều request cùng lúc nhân tổng tải.
- **Timeout của một API giới hạn toàn batch:** cần timeout riêng cho API, cho item và deadline tổng ở đúng ranh giới.
- **Flux.timeout luôn là deadline tổng:** nó thường giới hạn thời gian chờ tín hiệu đầu tiên hoặc khoảng cách giữa các tín hiệu; batch hữu hạn có thể dùng `collectList().timeout`.
- **Retry mọi lỗi đều an toàn:** chỉ retry lỗi tạm thời; thao tác ghi cần idempotency hoặc đối soát.
- **Fallback rỗng luôn giúp hệ thống resilient:** fallback có thể che giấu dữ liệu sai; chỉ dùng khi giá trị thay thế có ý nghĩa nghiệp vụ.
- **flatMap giữ thứ tự đầu vào:** kết quả có thể theo thứ tự inner hoàn tất; dùng `flatMapSequential` khi cần giữ thứ tự.
- **flatMapSequential không có buffer:** kết quả inner hoàn tất sớm có thể phải chờ inner trước để bảo toàn thứ tự.
- **Timeout hủy được mọi xử lý từ xa:** cancellation là yêu cầu dừng; server ngoài có thể đã thực hiện công việc.
- **collectList phù hợp với mọi Flux:** nó giữ tất cả kết quả trong bộ nhớ; chỉ dùng cho batch hữu hạn có giới hạn kích thước.
- **Dùng parallel scheduler để tăng số API call:** I/O non-blocking không cần một worker CPU cho mỗi request; điều khiển concurrency và connection pool ở đúng lớp.

## 21. Bài tập vận dụng

Một endpoint nhận tối đa 40 mã đơn hàng. Với mỗi đơn, service cần gọi Order API, Payment API và Delivery API để tạo `OrderSummary`. Order là bắt buộc; Payment có thể lấy dữ liệu cache khi API tạm thời không khả dụng; Delivery là tùy chọn và nếu không có dữ liệu thì hiển thị trạng thái "chưa có thông tin".

Hãy thiết kế pipeline:

1. Dùng kiểu Publisher nào cho một đơn hàng và cho toàn batch?
2. Những API nào có thể ghép bằng `Mono.zip`?
3. Làm sao biểu diễn Delivery rỗng mà không khiến zip hoàn tất rỗng?
4. Timeout riêng cho từng API nên là bao lâu so với deadline của một đơn?
5. Nếu một API cần retry, timeout nên đặt trước hay sau `retryWhen` để giới hạn từng lần thử?
6. Nếu concurrency theo đơn là 5 và mỗi đơn gọi ba API đồng thời, số lời gọi API đang hoạt động tối đa ước tính là bao nhiêu cho một batch?
7. Nếu cần giữ thứ tự đầu vào, chọn `flatMap`, `flatMapSequential` hay `concatMap`?
8. Làm thế nào để giới hạn tải tổng khi nhiều request batch đến cùng lúc?
9. Nếu một đơn thất bại, API nên trả lỗi toàn batch hay partial result? Nêu lý do theo hợp đồng.
10. Viết test cho timeout dependency, deadline batch, concurrency, thứ tự và cancellation.

**Gợi ý:** dùng `Mono<OrderSummary>` cho một đơn và `Mono<List<OrderSummary>>` cho batch hữu hạn. Dùng `defaultIfEmpty` cho Delivery nếu trạng thái không có dữ liệu được định nghĩa rõ. Dùng `Mono.zip` cho các nguồn độc lập; `flatMapSequential` với concurrency 5 để xử lý đồng thời nhưng giữ thứ tự. Mỗi API có timeout riêng, mỗi đơn có deadline, toàn batch có deadline tổng. Kết hợp giới hạn batch size, connection pool và bulkhead để bảo vệ dependency.

## Kết luận

Tổng hợp nhiều API hiệu quả cần phối hợp ba quyết định: ghép các nguồn độc lập bằng `Mono.zip`, giới hạn số workflow đang hoạt động bằng `flatMap` hoặc `flatMapSequential`, và đặt timeout ở từng API, từng mục tổng hợp cùng toàn batch. Concurrency phải được tính theo fan-out và số request đồng thời trên toàn ứng dụng; giới hạn của một `flatMap` không thay thế bulkhead hoặc connection pool. Retry chỉ áp dụng cho lỗi tạm thời, fallback phải đúng ngữ nghĩa nghiệp vụ, còn timeout và cancellation cần được kiểm thử ở đúng ranh giới. Khi có thêm metric về latency, connection, retry và queue, ta có thể điều chỉnh giới hạn theo năng lực thật của hệ thống thay vì phỏng đoán.
