# Chữ ký fallbackMethod và cách chọn theo kiểu ngoại lệ

Trong Resilience4j, annotation **@CircuitBreaker** có thể khai báo **fallbackMethod** để chọn một phương thức dự phòng khi lời gọi được bảo vệ thất bại hoặc bị Circuit Breaker từ chối. Phương thức fallback phải có kiểu trả về tương thích với phương thức gốc và nhận lại toàn bộ tham số đầu vào của phương thức gốc, sau đó thêm một tham số ngoại lệ ở cuối danh sách.

Khi cần xử lý nhiều loại lỗi, có thể khai báo nhiều phương thức fallback cùng tên nhưng khác kiểu ngoại lệ cuối cùng. Resilience4j chọn phương thức có kiểu ngoại lệ phù hợp nhất với lỗi thực tế. Nắm vững quy tắc chữ ký và lựa chọn exception giúp ứng dụng phân biệt timeout, Circuit Breaker OPEN, lỗi từ dịch vụ phụ thuộc và lỗi nghiệp vụ, đồng thời tránh fallback che giấu nguyên nhân thật.

## 1. Cấu trúc chữ ký của fallbackMethod

Giả sử phương thức gốc nhận một tham số là mã sản phẩm và trả về một đối tượng Product:

~~~java
@CircuitBreaker(name = "catalog", fallbackMethod = "getProductFallback")
public Product getProduct(String id) {
    return catalogClient.getProduct(id);
}
~~~

Phương thức fallback tương ứng có cùng tham số đầu vào, rồi thêm một tham số ngoại lệ ở cuối:

~~~java
private Product getProductFallback(
        String id,
        Throwable error) {
    return Product.unavailable(id);
}
~~~

Có ba quy tắc chính:

1. Tên phương thức fallback phải trùng với giá trị khai báo trong **fallbackMethod**.
2. Danh sách tham số của fallback phải giữ nguyên thứ tự và kiểu của các tham số phương thức gốc.
3. Tham số cuối cùng của fallback là một kiểu exception có thể nhận lỗi phát sinh, thường là **Throwable**, **Exception** hoặc một lớp ngoại lệ cụ thể.

Kiểu trả về của fallback cần tương thích với kiểu trả về của phương thức gốc. Nếu phương thức gốc trả về Product, fallback trả về Product. Nếu phương thức gốc trả về Mono<Product>, fallback cũng trả về Mono<Product>. Fallback không phải nơi thay đổi hợp đồng API của phương thức gốc.

## 2. Phương thức gốc có nhiều tham số

Fallback phải nhận lại tất cả tham số của phương thức gốc trước tham số exception. Ví dụ phương thức giữ hàng nhận mã SKU, mã kho và số lượng:

~~~java
@CircuitBreaker(name = "inventory", fallbackMethod = "reserveFallback")
public Reservation reserve(
        String sku,
        String warehouseCode,
        int quantity) {
    return inventoryClient.reserve(sku, warehouseCode, quantity);
}

private Reservation reserveFallback(
        String sku,
        String warehouseCode,
        int quantity,
        Throwable error) {
    return Reservation.unavailable(sku, warehouseCode, quantity);
}
~~~

Thứ tự tham số rất quan trọng. Chữ ký fallback phía trên tương ứng chính xác với ba tham số của phương thức gốc và thêm Throwable ở cuối. Không đặt exception lên đầu, không bỏ tham số quantity và không đổi kiểu int thành Integer nếu chữ ký không còn khớp với phương thức gốc theo yêu cầu của resolver.

Nếu phương thức gốc có tham số request object, fallback nhận lại đúng object đó:

~~~java
@CircuitBreaker(name = "payment", fallbackMethod = "authorizeFallback")
public PaymentResult authorize(PaymentRequest request, String traceId) {
    return paymentClient.authorize(request, traceId);
}

private PaymentResult authorizeFallback(
        PaymentRequest request,
        String traceId,
        Throwable error) {
    return PaymentResult.pending(request.orderId(), traceId);
}
~~~

Nhờ giữ lại tham số gốc, fallback có thể biết yêu cầu nào đang được xử lý, truy vấn cache hoặc tạo phản hồi phù hợp. Tuy nhiên, không nên ghi toàn bộ thông tin nhạy cảm của request vào log chỉ để chẩn đoán lỗi; hãy chọn trường cần thiết và dùng trace ID để liên kết log.

## 3. Chọn fallback theo kiểu ngoại lệ cụ thể

Có thể định nghĩa nhiều fallback cùng tên, mỗi phương thức nhận một lớp exception khác nhau ở tham số cuối. Ví dụ dịch vụ Catalog muốn xử lý riêng trường hợp Circuit Breaker đang OPEN, timeout và lỗi chưa phân loại:

~~~java
import java.util.concurrent.TimeoutException;

import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.annotation.CircuitBreaker;
import org.springframework.stereotype.Service;

@Service
class CatalogService {

    private final CatalogClient catalogClient;
    private final ProductCache productCache;

    CatalogService(
            CatalogClient catalogClient,
            ProductCache productCache) {
        this.catalogClient = catalogClient;
        this.productCache = productCache;
    }

    @CircuitBreaker(name = "catalog", fallbackMethod = "getProductFallback")
    public Product getProduct(String id) {
        return catalogClient.getProduct(id);
    }

    private Product getProductFallback(
            String id,
            CallNotPermittedException error) {
        log.warn("Circuit Breaker catalog từ chối lời gọi, id={}", id);
        return productCache.findById(id)
            .orElse(Product.unavailable(id));
    }

    private Product getProductFallback(
            String id,
            TimeoutException error) {
        log.warn("Catalog timeout, id={}", id);
        return productCache.findById(id)
            .orElse(Product.unavailable(id));
    }

    private Product getProductFallback(
            String id,
            Throwable error) {
        log.error("Không lấy được sản phẩm từ Catalog, id={}", id, error);
        return Product.unavailable(id);
    }
}
~~~

Các phương thức trên có cùng tên và cùng tham số nghiệp vụ là id. Chúng chỉ khác kiểu của tham số cuối cùng. Resilience4j tìm fallback có exception type tương thích nhất với loại lỗi thực tế. Nếu lỗi là **CallNotPermittedException**, phương thức chuyên biệt cho loại lỗi đó được ưu tiên hơn phương thức nhận Throwable. Nếu lỗi là TimeoutException, fallback timeout được chọn. Fallback nhận Throwable đóng vai trò phương án tổng quát cho các lỗi còn lại.

Đặt fallback cụ thể trước fallback tổng quát trong mã nguồn giúp người đọc dễ nhận biết ý định, dù việc chọn phương thức dựa trên kiểu exception chứ không dựa vào thứ tự khai báo. Tránh tạo nhiều fallback có cùng mức độ phù hợp khiến lựa chọn trở nên khó hiểu; mỗi loại lỗi nên có một phương án rõ ràng.

## 4. Cách resolver chọn exception phù hợp

Có thể hiểu quy tắc lựa chọn như việc tìm kiểu exception gần nhất trong hệ thống kế thừa Java. Giả sử exception thực tế là một lớp con của RuntimeException:

~~~java
private Product fallback(String id, RuntimeException error) {
    return Product.unavailable(id);
}

private Product fallback(String id, Exception error) {
    return Product.unavailable(id);
}

private Product fallback(String id, Throwable error) {
    return Product.unavailable(id);
}
~~~

Nếu lỗi thực tế là một RuntimeException, fallback nhận RuntimeException phù hợp cụ thể hơn so với fallback nhận Exception hoặc Throwable. Nếu lỗi thực tế là một lớp con riêng của RuntimeException và có fallback dành riêng cho lớp đó, phương thức chuyên biệt sẽ được ưu tiên.

Bảng minh họa:

| Kiểu lỗi thực tế | Các fallback có sẵn | Fallback phù hợp hơn |
|---|---|---|
| **CallNotPermittedException** | CallNotPermittedException, RuntimeException, Throwable | CallNotPermittedException |
| **TimeoutException** | Exception, Throwable | Exception |
| **InvalidProductException** (extends RuntimeException) | InvalidProductException, RuntimeException, Throwable | InvalidProductException |
| Một lỗi không có fallback riêng | Throwable | Throwable |

Không cần tự viết chuỗi if/else để kiểm tra mọi exception nếu chỉ cần chọn theo kiểu. Việc overload fallback giúp khai báo chính sách gần với kiểu lỗi và giữ phần xử lý dễ đọc. Nếu cần phân loại theo thuộc tính của exception, chẳng hạn mã HTTP hoặc mã nghiệp vụ, có thể kiểm tra trong thân fallback phù hợp.

Nếu exception được bọc trong một lớp khác, resolver làm việc với exception được chuyển đến fallback. Không nên giả định nó luôn tự chọn theo cause sâu nhất. Khi cần, hãy kiểm tra **getCause()** và phân loại nguyên nhân gốc có chủ đích, đồng thời giữ lại exception ban đầu khi ghi log.

## 5. Dùng Throwable làm fallback tổng quát

Một fallback nhận Throwable có thể nhận nhiều loại lỗi và hữu ích làm nhánh dự phòng cuối cùng:

~~~java
private Product getProductFallback(String id, Throwable error) {
    log.error("Lỗi khi lấy sản phẩm, id={}", id, error);
    return Product.unavailable(id);
}
~~~

Tuy nhiên, fallback tổng quát có thể che khuất lỗi nghiệp vụ hoặc lỗi lập trình nếu luôn trả về dữ liệu mặc định. Ví dụ, nếu lỗi là InvalidProductIdException do client gửi dữ liệu sai, trả về Product.unavailable có thể khiến caller hiểu nhầm rằng Catalog tạm thời không khả dụng.

Với những lỗi cần được trả về như lỗi nghiệp vụ, hãy khai báo fallback chuyên biệt để ném lại hoặc chuyển đổi có chủ đích:

~~~java
private Product getProductFallback(
        String id,
        InvalidProductIdException error) {
    throw error;
}

private Product getProductFallback(
        String id,
        CallNotPermittedException error) {
    return productCache.findById(id)
        .orElse(Product.unavailable(id));
}

private Product getProductFallback(String id, Throwable error) {
    log.error("Catalog gặp lỗi không phân loại, id={}", id, error);
    return Product.unavailable(id);
}
~~~

Trong ví dụ, lỗi đầu vào không bị biến thành lỗi dịch vụ. Lời gọi bị Circuit Breaker từ chối có thể dùng cache; các lỗi còn lại có fallback chung. Hãy xác định rõ exception nào được xem là lỗi kỹ thuật, exception nào là kết quả nghiệp vụ và exception nào cần truyền tiếp cho tầng gọi.

## 6. Chữ ký fallback với kiểu trả về reactive

Với ứng dụng WebFlux, phương thức gốc thường trả về Mono hoặc Flux. Fallback cần trả về cùng kiểu Publisher và vẫn nhận các tham số gốc trước exception.

Ví dụ với Mono:

~~~java
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
class ReactiveCatalogService {

    private final ReactiveCatalogClient catalogClient;
    private final ProductCache productCache;

    ReactiveCatalogService(
            ReactiveCatalogClient catalogClient,
            ProductCache productCache) {
        this.catalogClient = catalogClient;
        this.productCache = productCache;
    }

    @CircuitBreaker(name = "catalog", fallbackMethod = "getProductFallback")
    public Mono<Product> getProduct(String id) {
        return catalogClient.getProduct(id);
    }

    private Mono<Product> getProductFallback(
            String id,
            CallNotPermittedException error) {
        return productCache.findByIdReactive(id)
            .switchIfEmpty(Mono.just(Product.unavailable(id)));
    }

    private Mono<Product> getProductFallback(
            String id,
            Throwable error) {
        return Mono.just(Product.unavailable(id));
    }
}
~~~

Với Flux, fallback trả về Flux:

~~~java
@CircuitBreaker(name = "catalog-search", fallbackMethod = "searchFallback")
public Flux<Product> search(String keyword, int limit) {
    return catalogClient.search(keyword, limit);
}

private Flux<Product> searchFallback(
        String keyword,
        int limit,
        Throwable error) {
    return productCache.search(keyword, limit);
}
~~~

Không trả Product trực tiếp từ fallback của phương thức trả về Mono<Product>; cũng không trả Mono<Product> từ fallback của phương thức trả về Flux<Product>. Giữ kiểu Publisher nhất quán để caller tiếp tục xử lý bằng reactive operators.

Fallback reactive nên tạo Publisher dự phòng và không gọi **block()**. Nếu fallback truy vấn cache qua một client reactive, hãy giữ thao tác đó trong Mono/Flux. Nếu cache API chỉ blocking, cần chuyển thao tác sang scheduler phù hợp hoặc cung cấp một API non-blocking.

## 7. Fallback với các kiểu trả về bất đồng bộ khác

Resilience4j cũng hỗ trợ các kiểu trả về bất đồng bộ mà integration tương ứng xử lý, chẳng hạn CompletionStage. Fallback cần trả về kiểu tương thích với phương thức gốc:

~~~java
@CircuitBreaker(name = "catalog", fallbackMethod = "getProductAsyncFallback")
public CompletionStage<Product> getProductAsync(String id) {
    return catalogClient.getProductAsync(id);
}

private CompletionStage<Product> getProductAsyncFallback(
        String id,
        Throwable error) {
    return CompletableFuture.completedFuture(Product.unavailable(id));
}
~~~

Ví dụ minh họa hợp đồng kiểu trả về: phương thức gốc trả CompletionStage<Product>, fallback cũng trả CompletionStage<Product>. Khi sử dụng TimeLimiter hoặc các annotation bất đồng bộ kết hợp với Circuit Breaker, cần kiểm tra thứ tự aspect và khả năng hỗ trợ của phiên bản Resilience4j đang dùng.

Không dùng fallback đồng bộ trả về Product cho một phương thức có hợp đồng CompletionStage<Product> nếu integration yêu cầu fallback cùng kiểu. Việc giữ kiểu trả về nhất quán làm rõ thời điểm hoàn tất và cách caller nhận kết quả.

## 8. FallbackMethod và các lỗi thường gặp

Một số lỗi phổ biến khiến Resilience4j không tìm được fallback hoặc chọn nhánh không như mong đợi:

| Lỗi | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Không tìm thấy fallback | Sai tên trong annotation | Kiểm tra chính xác giá trị fallbackMethod |
| Không khớp chữ ký | Thiếu tham số gốc, sai thứ tự hoặc sai kiểu | Sao chép đầy đủ tham số phương thức gốc rồi thêm exception cuối |
| Sai kiểu trả về | Fallback trả về kiểu không tương thích | Dùng cùng kiểu trả về với phương thức gốc |
| Chọn nhánh tổng quát ngoài ý muốn | Không có fallback cho exception cụ thể hoặc exception thực tế bị bọc | Kiểm tra kiểu exception được truyền và cause |
| Lỗi nghiệp vụ bị che | Throwable fallback luôn trả dữ liệu mặc định | Thêm fallback chuyên biệt để ném lại hoặc chuyển lỗi nghiệp vụ |
| Fallback lại thất bại | Cache hoặc logic dự phòng ném exception | Thiết kế fallback đơn giản, có nguồn độc lập và theo dõi lỗi fallback |
| Annotation không được áp dụng | Lời gọi không đi qua Spring AOP proxy | Gọi method qua bean proxy thay vì self-invocation trong cùng bean |

Nếu không có fallback phù hợp, lỗi gốc thường tiếp tục được truyền ra ngoài. Nếu fallback được tìm thấy nhưng chính fallback ném lỗi, caller nhận lỗi phát sinh từ fallback. Vì vậy, cần kiểm tra cả lỗi của operation và lỗi của hành vi dự phòng.

## 9. Annotation hoạt động qua Spring AOP proxy

Annotation **@CircuitBreaker** được xử lý qua aspect của Resilience4j trong Spring. Spring AOP cần intercept lời gọi đến bean được quản lý bởi container. Nếu một method trong cùng class gọi trực tiếp một method khác cũng có annotation, lời gọi nội bộ đó thường không đi qua proxy và advice có thể không được kích hoạt.

Ví dụ không nên dựa vào self-invocation:

~~~java
@Service
class ProductService {

    public Product load(String id) {
        // Gọi nội bộ method annotated, không đi qua Spring proxy.
        return loadFromCatalog(id);
    }

    @CircuitBreaker(name = "catalog", fallbackMethod = "loadFallback")
    public Product loadFromCatalog(String id) {
        return catalogClient.getProduct(id);
    }

    private Product loadFallback(String id, Throwable error) {
        return Product.unavailable(id);
    }
}
~~~

Một cách tổ chức rõ ràng là đặt method được bảo vệ trong một bean riêng và inject bean đó vào service gọi:

~~~java
@Service
class CatalogGateway {

    @CircuitBreaker(name = "catalog", fallbackMethod = "getFallback")
    public Product get(String id) {
        return catalogClient.getProduct(id);
    }

    private Product getFallback(String id, Throwable error) {
        return Product.unavailable(id);
    }
}

@Service
class ProductService {

    private final CatalogGateway catalogGateway;

    ProductService(CatalogGateway catalogGateway) {
        this.catalogGateway = catalogGateway;
    }

    Product load(String id) {
        return catalogGateway.get(id);
    }
}
~~~

Ở đây, ProductService gọi CatalogGateway thông qua bean do Spring quản lý, nên lời gọi có thể đi qua proxy và được aspect xử lý. Khi thiết kế annotation, hãy xác nhận dependency AOP và Resilience4j Spring integration đã được cấu hình đúng, method thực sự được gọi qua proxy và fallback nằm trong phạm vi mà resolver có thể tìm thấy.

## 10. Kết hợp fallback với CallNotPermittedException và timeout

Một fallback có thể phân nhánh theo nguyên nhân để chọn hành vi phù hợp. Ví dụ:

~~~java
@CircuitBreaker(name = "inventory", fallbackMethod = "getStockFallback")
public Stock getStock(String sku) {
    return inventoryClient.getStock(sku);
}

private Stock getStockFallback(
        String sku,
        CallNotPermittedException error) {
    log.warn("Inventory đang OPEN, sku={}", sku);
    return inventoryCache.findBySku(sku)
        .orElse(Stock.unavailable(sku));
}

private Stock getStockFallback(
        String sku,
        TimeoutException error) {
    log.warn("Inventory timeout, sku={}", sku);
    return inventoryCache.findBySku(sku)
        .orElse(Stock.unavailable(sku));
}

private Stock getStockFallback(String sku, Throwable error) {
    log.error("Lỗi không phân loại từ Inventory, sku={}", sku, error);
    return Stock.unavailable(sku);
}
~~~

**CallNotPermittedException** thể hiện Circuit Breaker từ chối lời gọi trước khi supplier thực thi. Timeout thể hiện thao tác đã được cho phép nhưng không hoàn tất trong thời hạn được đặt bởi cơ chế timeout. Hai trường hợp có thể dùng cùng cache nhưng nên được ghi nhận riêng để dashboard và log thể hiện đúng nguyên nhân.

Nếu annotation @CircuitBreaker được dùng độc lập, timeout có thể do HTTP client hoặc thao tác được bảo vệ phát ra. Khi kết hợp TimeLimiter, Retry hoặc Bulkhead, exception thực tế được chuyển đến fallback còn phụ thuộc thứ tự các aspect và cách tích hợp. Hãy kiểm tra exception nhận được ở runtime thay vì giả định mọi timeout đều có đúng một lớp exception cố định.

Không nên để fallback gọi lại chính phương thức được bảo vệ qua cùng proxy mà không có giới hạn, vì có thể tạo vòng lặp fallback hoặc tiếp tục đi qua Circuit Breaker đang OPEN. Fallback nên dùng cache, nguồn dự phòng độc lập hoặc trả lỗi có ý nghĩa.

## 11. Thiết kế fallback dễ bảo trì

Một fallback tốt cần thể hiện rõ cách ứng dụng phản ứng với lỗi, đồng thời giữ đúng ý nghĩa dữ liệu.

- **Giữ kiểu trả về:** Product thì trả Product; Mono<Product> thì trả Mono<Product>.
- **Giữ tham số gốc:** fallback cần biết request nào đang được xử lý.
- **Chọn exception cụ thể:** tách lỗi bị từ chối, timeout và lỗi nghiệp vụ khi hành vi cần khác nhau.
- **Có nhánh tổng quát khi cần:** Throwable fallback có thể làm phương án cuối, nhưng không nên che mọi lỗi bằng giá trị giả.
- **Không phụ thuộc vào nguồn đang lỗi:** dùng cache hoặc dịch vụ dự phòng độc lập.
- **Ghi log vừa đủ:** giữ exception và trace ID, tránh ghi dữ liệu nhạy cảm.
- **Kiểm tra lỗi của fallback:** cache cũng có thể lỗi hoặc không có dữ liệu; cần quy định rõ kết quả khi đó.

Với lỗi nghiệp vụ, có thể ném lại exception gốc hoặc chuyển thành kiểu kết quả nghiệp vụ riêng. Với lỗi hạ tầng, có thể dùng dữ liệu cache nếu độ cũ của cache được nghiệp vụ chấp nhận. Không trả dữ liệu mặc định khiến caller hiểu nhầm rằng dependency đã xác nhận một kết quả hợp lệ.

## 12. Tình huống thực hành

Một dịch vụ đặt hàng gọi Catalog để lấy thông tin sản phẩm và Inventory để kiểm tra tồn kho. Mỗi method dùng Circuit Breaker riêng và có fallback theo exception.

- Catalog dùng fallback cache khi Circuit Breaker OPEN.
- Catalog dùng fallback riêng khi timeout.
- SKU không hợp lệ được chuyển tiếp thành lỗi nghiệp vụ.
- Inventory dùng fallback đánh dấu trạng thái không khả dụng khi dịch vụ không phản hồi.
- Các fallback tổng quát chỉ xử lý lỗi chưa được phân loại.

Ví dụ cho Catalog:

~~~java
@CircuitBreaker(name = "catalog", fallbackMethod = "findFallback")
public Product find(String id) {
    return catalogClient.getProduct(id);
}

private Product findFallback(
        String id,
        CallNotPermittedException error) {
    return productCache.findById(id)
        .orElse(Product.unavailable(id));
}

private Product findFallback(
        String id,
        InvalidProductIdException error) {
    throw error;
}

private Product findFallback(String id, Throwable error) {
    log.error("Catalog request failed, id={}", id, error);
    return Product.unavailable(id);
}
~~~

Khi kiểm thử, hãy tạo các tình huống riêng:

1. Circuit Breaker OPEN và lời gọi bị từ chối; xác nhận fallback nhận CallNotPermittedException.
2. Client phát TimeoutException; xác nhận fallback timeout được chọn nếu exception này được chuyển trực tiếp.
3. Client phát InvalidProductIdException; xác nhận lỗi nghiệp vụ được truyền tiếp.
4. Client phát exception không có fallback chuyên biệt; xác nhận nhánh Throwable được dùng.
5. Fallback cache cũng thất bại; xác nhận caller nhận lỗi từ fallback và log giữ nguyên nguyên nhân.
6. Gọi method annotated từ một bean khác; so sánh với self-invocation để kiểm tra AOP proxy.

Các câu hỏi cần trả lời sau khi thực hành:

- Fallback nhận tham số gốc theo thứ tự nào?
- Exception phải nằm ở vị trí nào trong chữ ký?
- Resilience4j chọn fallback nào khi có nhiều overload?
- Khi nào nên dùng Throwable và khi nào cần exception cụ thể?
- Vì sao fallback reactive phải trả Mono hoặc Flux?
- Self-invocation ảnh hưởng thế nào đến annotation?

## Kết luận

Với Resilience4j **fallbackMethod**, fallback giữ nguyên kiểu trả về và toàn bộ tham số của phương thức gốc, sau đó thêm exception ở cuối. Có thể overload cùng tên fallback để xử lý riêng CallNotPermittedException, timeout hoặc lỗi nghiệp vụ; resolver chọn kiểu exception phù hợp nhất với lỗi thực tế. Giữ một nhánh tổng quát khi cần, tránh che giấu lỗi nghiệp vụ, duy trì kiểu Publisher cho reactive và bảo đảm lời gọi annotated đi qua Spring AOP proxy để cơ chế Circuit Breaker cùng fallback được thực thi đúng.
