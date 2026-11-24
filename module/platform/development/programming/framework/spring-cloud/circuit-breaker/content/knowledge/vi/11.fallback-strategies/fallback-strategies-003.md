# Trả kết quả suy giảm chức năng mà vẫn đúng hợp đồng

Khi dịch vụ phụ thuộc chậm hoặc không khả dụng, fallback giúp ứng dụng tiếp tục phục vụ một phần nhu cầu thay vì để mọi request thất bại. Tuy nhiên, fallback chỉ hữu ích khi kết quả thay thế vẫn tuân thủ hợp đồng mà caller hiểu được. Một response có cấu trúc hợp lệ nhưng âm thầm chứa dữ liệu giả, dữ liệu quá cũ hoặc trạng thái nghiệp vụ sai có thể gây lỗi khó phát hiện hơn việc trả lỗi rõ ràng.

Với Spring Cloud Circuit Breaker và Resilience4j, fallback có thể trả một kết quả suy giảm chức năng (degraded result), chẳng hạn dữ liệu cache có đánh dấu thời điểm cập nhật, một phần dữ liệu không phụ thuộc vào dịch vụ đang lỗi, hoặc trạng thái “tạm thời không có dữ liệu”. Thiết kế cần giữ kiểu dữ liệu, ý nghĩa trường, quy tắc nghiệp vụ và cách caller xử lý kết quả.

## Hợp đồng kết quả phải nói rõ điều gì đã xảy ra

Giả sử API danh mục trả thông tin sản phẩm. Nếu dịch vụ catalog không phản hồi, fallback có thể lấy bản sao từ cache. Caller vẫn nhận cùng một kiểu response, nhưng cần biết đó là dữ liệu cache và biết dữ liệu được cập nhật lần cuối khi nào.

Một hợp đồng kết quả nên phân biệt ít nhất:

- **Dữ liệu trực tiếp:** được lấy thành công từ dịch vụ phụ thuộc.
- **Dữ liệu suy giảm:** có thể là bản cache cũ, dữ liệu tổng hợp hoặc một phần kết quả; cần mô tả nguồn và mức độ đầy đủ.
- **Không có dữ liệu thay thế:** ứng dụng không thể trả một kết quả nghiệp vụ đáng tin cậy; khi đó phải trả lỗi phù hợp hoặc trạng thái không khả dụng rõ ràng.

Ví dụ, response có thể dùng trường `availability` và `dataAsOf` để biểu đạt nguồn và độ mới:

```java
public enum Availability {
    LIVE,
    DEGRADED,
    UNAVAILABLE
}

public enum DataSource {
    CATALOG,
    CACHE,
    NONE
}

public record ProductView(
        String productId,
        String name,
        Availability availability,
        DataSource source,
        Instant dataAsOf
) {
    public static ProductView fromCatalog(Product product) {
        return new ProductView(
                product.id(), product.name(),
                Availability.LIVE, DataSource.CATALOG, Instant.now());
    }

    public static ProductView fromCache(CachedProduct product) {
        return new ProductView(
                product.id(), product.name(),
                Availability.DEGRADED, DataSource.CACHE,
                product.updatedAt());
    }

    public static ProductView unavailable(String productId) {
        return new ProductView(
                productId, null,
                Availability.UNAVAILABLE, DataSource.NONE, null);
    }
}
```

`ProductView` giữ một schema thống nhất cho cả ba trạng thái. Caller không phải đoán dữ liệu đến từ đâu hoặc xem một tên sản phẩm rỗng là “không tìm thấy” hay “dịch vụ đang lỗi”. Nếu API hiện tại đã có schema công khai, hãy mở rộng theo cách tương thích ngược và thống nhất với consumer trước khi thay đổi các trường bắt buộc.

Không nên đặt giá trị mặc định có vẻ hợp lệ cho dữ liệu quan trọng. Ví dụ, trả giá sản phẩm bằng `0`, số dư bằng `0` hoặc trạng thái đơn hàng là `COMPLETED` chỉ để response không rỗng có thể khiến caller thực hiện quyết định sai. Nếu không thể tạo một kết quả thay thế đúng nghĩa nghiệp vụ, hãy biểu diễn không khả dụng hoặc trả lỗi có thể xử lý.

## Chọn dữ liệu thay thế theo quy tắc nghiệp vụ

Fallback nên có thứ tự ưu tiên rõ ràng. Với API đọc catalog, một chiến lược thường dùng là:

1. Dùng dữ liệu trực tiếp khi dịch vụ phụ thuộc phản hồi thành công.
2. Khi request thất bại, tìm bản cache có đủ trường cần thiết và còn trong giới hạn tuổi dữ liệu cho phép.
3. Nếu cache không tồn tại hoặc quá cũ, trả trạng thái không khả dụng theo hợp đồng API.

```java
public ProductView getProduct(String productId) {
    CircuitBreaker breaker = circuitBreakerFactory.create("catalog");

    return breaker.run(
            () -> ProductView.fromCatalog(catalogClient.findProduct(productId)),
            error -> cache.findProduct(productId)
                    .filter(cached -> cached.isFreshWithin(Duration.ofMinutes(15)))
                    .map(ProductView::fromCache)
                    .orElseGet(() -> ProductView.unavailable(productId))
    );
}
```

Ví dụ giả định `cache.findProduct` là thao tác local nhanh, không gọi lại catalog. Giới hạn 15 phút chỉ là giá trị minh họa; tuổi dữ liệu tối đa phải xuất phát từ yêu cầu nghiệp vụ. Giá và tồn kho có thể cần giới hạn chặt hơn mô tả sản phẩm. Dữ liệu cá nhân, quyền truy cập, trạng thái thanh toán hoặc trạng thái đơn hàng thường không được phép dùng bản cache cũ nếu có thể làm sai quyết định hoặc tiết lộ thông tin.

Fallback không nên gọi lại chính dịch vụ đã thất bại qua một client hoặc đường mạng khác mà không có chủ đích. Làm vậy có thể tạo thêm tải đúng lúc dịch vụ đang suy yếu và kéo dài chuỗi lỗi. Ưu tiên nguồn thay thế độc lập như cache local, read replica có giới hạn, dữ liệu tĩnh đã được phê duyệt hoặc kết quả suy giảm được tính trước.

## Phân biệt lỗi kỹ thuật và kết quả nghiệp vụ

Không phải mọi trường hợp đều nên kích hoạt cùng một fallback. Một request không tìm thấy sản phẩm là kết quả nghiệp vụ hợp lệ; timeout khi gọi catalog là lỗi kỹ thuật; request sai định dạng là lỗi đầu vào của caller. Nếu gom tất cả vào một kết quả suy giảm, ứng dụng có thể che giấu lỗi lập trình hoặc biến “không tìm thấy” thành “dịch vụ tạm thời không khả dụng”.

Hãy xác định exception nào được circuit breaker ghi nhận là lỗi, exception nào được bỏ qua và exception nào cần truyền thẳng lên caller. Có thể dùng `recordExceptions`, `ignoreExceptions`, `recordExceptionPredicate` hoặc `ignoreExceptionPredicate` trong Resilience4j tùy phiên bản và cấu hình.

| Tình huống | Cách xử lý thường phù hợp |
|---|---|
| Timeout hoặc lỗi kết nối tới dịch vụ phụ thuộc | Có thể dùng fallback cache nếu dữ liệu còn đủ mới |
| Circuit breaker từ chối lời gọi khi `OPEN` | Dùng cùng chính sách fallback đã được thiết kế cho lỗi phụ thuộc |
| Sản phẩm không tồn tại theo phản hồi nghiệp vụ | Trả kết quả not found theo hợp đồng; không giả lập dữ liệu cache |
| Request không hợp lệ hoặc không được phép | Trả lỗi validation/authorization; không che bằng dữ liệu dự phòng |
| Cache lỗi hoặc quá cũ | Trả trạng thái không khả dụng hoặc exception được ánh xạ rõ ràng |

Fallback cũng có thể kiểm tra nguyên nhân lỗi để chọn hành động. Tuy nhiên, không nên dựa vào tên exception đơn lẻ nếu backend có thể bọc exception. Hãy kiểm tra cause chain hoặc predicate theo kiểu exception thực tế và giữ chính sách phân loại nhất quán.

## Giữ rõ ý nghĩa HTTP response

Việc fallback trả một DTO không tự quyết định HTTP status. Controller hoặc tầng ánh xạ API phải xác định trạng thái phù hợp với hợp đồng:

- Nếu dữ liệu cache được xem là kết quả đọc hợp lệ và schema có `availability=DEGRADED`, API có thể trả `200 OK` cùng metadata thể hiện dữ liệu cũ.
- Nếu không có kết quả thay thế có thể sử dụng, API có thể trả `503 Service Unavailable` hoặc mã lỗi nghiệp vụ đã được quy định.
- Nếu caller cần thử lại sau, cân nhắc `Retry-After` khi thời điểm thử lại có ý nghĩa và có thể ước lượng.

Không trả `200 OK` với một object rỗng nếu consumer sẽ hiểu nó là một kết quả nghiệp vụ bình thường. Ngược lại, không nhất thiết trả `503` chỉ vì dùng cache: nếu API cho phép dữ liệu cache và công bố rõ độ mới, response đó vẫn có thể đáp ứng hợp đồng.

Ví dụ ánh xạ response suy giảm:

```java
@GetMapping("/products/{id}")
public ResponseEntity<ProductView> getProduct(@PathVariable String id) {
    ProductView result = catalogService.getProduct(id);

    if (result.availability() == Availability.UNAVAILABLE) {
        return ResponseEntity.status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(result);
    }

    return ResponseEntity.ok()
            .header("X-Data-Availability", result.availability().name())
            .body(result);
}
```

Đây là một lựa chọn thiết kế. Nếu API hiện tại đã quy định status code hoặc error envelope khác, hãy tuân thủ hợp đồng hiện có và biểu đạt trạng thái suy giảm bằng trường hoặc metadata tương thích.

## Fallback với reactive publisher

Với Spring Cloud `ReactiveCircuitBreaker`, fallback cần trả về cùng loại publisher và kiểu phần tử với nguồn. Có thể dùng cache reactive hoặc phát một kết quả suy giảm đã được định nghĩa:

```java
public Mono<ProductView> getProduct(String productId) {
    ReactiveCircuitBreaker breaker =
            circuitBreakerFactory.create("catalog");

    Mono<ProductView> request = Mono.defer(() ->
            catalogClient.findProduct(productId)
                    .map(ProductView::fromCatalog)
    );

    return breaker.run(request, error ->
            cache.findProduct(productId)
                    .filter(cached -> cached.isFreshWithin(Duration.ofMinutes(15)))
                    .map(ProductView::fromCache)
                    .switchIfEmpty(Mono.just(ProductView.unavailable(productId)))
    );
}
```

Fallback trả `Mono<ProductView>` và không tự subscribe. `switchIfEmpty` ở đây xử lý trường hợp cache không có bản ghi hoặc bản ghi không đạt giới hạn tuổi. Nếu cache client có thể phát lỗi, cần quyết định cách xử lý lỗi cache riêng; không để lỗi của fallback vô tình tạo một response không đúng hợp đồng.

Với `Flux`, cân nhắc kỹ việc dùng `Flux.empty()` làm fallback. Một luồng rỗng có thể có nghĩa là “không có kết quả phù hợp”, trong khi tình huống thật là “dịch vụ tìm kiếm không khả dụng”. Nếu hai ý nghĩa khác nhau, hãy trả một kiểu envelope có metadata trạng thái hoặc phát lỗi được ánh xạ thành response lỗi.

## Fallback không làm mất dấu lỗi gốc

Khi circuit breaker thực thi supplier và supplier thất bại, backend đánh giá lần gọi gốc theo cấu hình của nó. Fallback cung cấp kết quả thay thế cho caller; việc fallback trả thành công không có nghĩa dịch vụ phụ thuộc đã hoạt động tốt. Nếu fallback che hết lỗi bằng một giá trị mặc định, dashboard có thể cho thấy tỷ lệ request của API ngoài thành công trong khi circuit breaker vẫn ghi nhận nhiều lỗi ở dependency.

Vì vậy, hãy quan sát riêng:

- Tỷ lệ lỗi và lời gọi chậm của circuit breaker.
- Tỷ lệ fallback được gọi và nguyên nhân kích hoạt.
- Tỷ lệ response suy giảm, nguồn dữ liệu và tuổi dữ liệu.
- Tỷ lệ fallback thất bại hoặc không có dữ liệu thay thế.

Log nên chứa correlation ID, tên dependency, loại lỗi, quyết định fallback và nguồn dữ liệu. Tránh ghi thông tin nhạy cảm hoặc toàn bộ payload. Metric nên dùng nhãn có cardinality giới hạn; không gắn product ID, user ID hoặc request ID làm label.

## Kiểm thử hợp đồng và giới hạn suy giảm

Kiểm thử fallback không chỉ xác nhận “không ném exception”. Cần xác nhận caller nhận đúng schema, đúng trạng thái, dữ liệu đúng nguồn và không vượt giới hạn tuổi dữ liệu.

| Kịch bản | Kết quả cần xác nhận |
|---|---|
| Catalog trả dữ liệu trực tiếp | `availability=LIVE`, `source=CATALOG` và dữ liệu khớp |
| Catalog timeout, cache còn mới | `availability=DEGRADED`, `source=CACHE`, `dataAsOf` giữ timestamp cache |
| Catalog lỗi, cache quá cũ | Trả trạng thái `UNAVAILABLE` hoặc lỗi theo hợp đồng |
| Breaker `OPEN` | Supplier không được gọi; fallback áp dụng cùng chính sách |
| Sản phẩm không tồn tại | Trả not found, không biến thành dữ liệu cache mặc định |
| Cache phát lỗi | Ánh xạ lỗi fallback rõ ràng, không trả object giả hợp lệ |

Ví dụ kiểm thử service có thể dùng mock để điều khiển dependency và cache:

```java
when(catalogClient.findProduct("p-10"))
        .thenThrow(new TimeoutException("catalog timeout"));
when(cache.findProduct("p-10"))
        .thenReturn(Optional.of(freshCachedProduct));

ProductView result = catalogService.getProduct("p-10");

assertEquals(Availability.DEGRADED, result.availability());
assertEquals(DataSource.CACHE, result.source());
assertEquals(freshCachedProduct.updatedAt(), result.dataAsOf());
```

Trong kiểm thử tích hợp, nên điều khiển circuit breaker sang `OPEN` hoặc tạo đủ lỗi để breaker chuyển trạng thái, sau đó xác nhận supplier không được gọi. Với reactive, dùng `StepVerifier` để xác nhận publisher fallback phát đúng trạng thái và không tự thực thi trước subscription.

## Nguyên tắc thiết kế

Một kết quả suy giảm tốt phải giúp caller đưa ra quyết định an toàn. Hãy giữ schema và ý nghĩa trường rõ ràng; công bố nguồn và độ mới; chỉ dùng cache khi nghiệp vụ cho phép; phân biệt lỗi kỹ thuật với kết quả nghiệp vụ; giữ fallback độc lập, nhanh và có giới hạn; và theo dõi riêng lỗi gốc với kết quả suy giảm. Nếu không thể tạo dữ liệu thay thế đáng tin cậy, trả trạng thái không khả dụng một cách minh bạch sẽ bảo vệ hợp đồng tốt hơn việc giả vờ request đã thành công.
